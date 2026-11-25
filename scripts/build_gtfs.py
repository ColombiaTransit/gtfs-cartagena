#!/usr/bin/env python3
"""
Build the static GTFS feed for Transcaribe from the API snapshot (raw/m2m/),
the GraphHopper running times (data/running_times.csv) and the holiday
calendar. See docs/gtfs-design.md for the model and the identifiers.

Usage: python scripts/build_gtfs.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]  (default: today + 182 days)
Writes build/gtfs/*.txt and build/transcaribe-gtfs.zip.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gtfs_calendar  # noqa: E402
from match_stops import Line, latlon, norm, xy  # noqa: E402
from running_times import orient, positions  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
M2M = ROOT / "raw" / "m2m"
BUILD = ROOT / "build"
OUT = BUILD / "gtfs"

EXCLUDE = ("A000",)                    # test lines
# one sample date per service day type; the snapshot shows all weekdays are equal
SAMPLE_DATES = {"weekday": ["2026-11-26", "2026-11-20", "2026-11-23"],
                "saturday": ["2026-11-21"], "sunday": ["2026-11-22"]}
DWELL_STREET = 20                      # s at a street stop
DWELL_STATION = 30                     # s at a trunk station platform
FALLBACK_KMH = 20                      # where GraphHopper has nothing usable
ROUTE_TYPES = {"T": ("Troncal", "E4572E"), "X": ("Pretroncal", "2E86AB"),
               "A": ("Alimentadora", "2D7246"), "C": ("Complementaria", "00A6A6")}
CODE = re.compile(r"^(?P<base>.*?)\s+(?P<code>[A-F]\d|desc)$", re.I)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def hms(sec: float) -> str:
    s = int(round(sec))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def write(name: str, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or list(rows[0])
    with (OUT / name).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def stations_from_repo() -> dict[str, dict]:
    """Trunk stations (name, position) from data/stops.csv, keyed by normalised name."""
    out = {}
    path = ROOT / "data" / "stops.csv"
    for r in csv.DictReader(path.open(encoding="utf-8")) if path.exists() else []:
        if r["location_type"] == "1":
            out[norm(r["stop_name"])] = {"id": r["stop_id"], "name": r["stop_name"],
                                         "lat": float(r["stop_lat"]), "lon": float(r["stop_lon"])}
    # names the API uses for them
    for alias, target in {"delicias": "las delicias", "chambacu": "chambacu", "los angeles": "los angeles",
                          "maria auxiliadora": "maria auxiliadora", "republica del libano": "republica del libano",
                          "transferencia santa lucia": "santa lucia"}.items():
        if target in out:
            out.setdefault(alias, out[target])
    return out


def station_of(name: str, stations: dict) -> tuple[dict, str] | None:
    m = CODE.match(name.strip())
    base, code = (m["base"], m["code"].upper() if m["code"].lower() != "desc" else "DESC") if m else (name.strip(), "")
    st = stations.get(norm(base))
    return (st, code) if st else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=date.today().isoformat())
    ap.add_argument("--end", default=None, help="default: START + 182 days")
    args = ap.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else start + timedelta(days=182)
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.txt"):
        f.unlink()

    lines = [l for l in read_json(M2M / "allLines.json") if not str(l["numero"]).startswith(EXCLUDE)]
    points = {p["id"]: p for p in read_json(M2M / "allPoints.json")}
    patterns = {}
    for l in lines:
        for p in read_json(M2M / "pattern" / f"{l['id']}.json"):
            patterns[p["id"]] = p
    stations = stations_from_repo()

    # open-data names of the first/last stop per route and direction, for terminals
    od_ends = {}
    sp = ROOT / "data" / "stop_positions.csv"
    if sp.exists():
        rows = list(csv.DictReader(sp.open(encoding="utf-8")))
        for r in rows:
            od_ends.setdefault((r["route"], r["direction"], "first"), r["name"])
            od_ends[(r["route"], r["direction"], "last")] = r["name"]

    # running times per variant and leg
    legs = defaultdict(dict)
    for r in csv.DictReader((ROOT / "data" / "running_times.csv").open(encoding="utf-8")):
        legs[int(r["variant"])][int(r["seq"])] = r

    def direction(nome: str) -> str:
        n = nome.upper()
        return "VUELTA" if "VUELTA" in n else "CIRCULAR" if "CIRCULAR" in n else "IDA"

    # ---------------------------------------------------------------- variants
    variants = []
    terminal_names: dict[int, Counter] = defaultdict(Counter)
    terminal_pts: dict[int, list] = defaultdict(list)
    for l in lines:
        for t in l["trajetos"]:
            vid = t["id_migracao"]
            pat = patterns.get(vid)
            bus = read_json(M2M / "bustop" / f"{vid}.json")
            if not pat or len(pat["polyLine"]) < 2:
                print(f"skip {l['numero']} {vid}: no geometry", file=sys.stderr)
                continue
            raw = [(p["lat"], p["lng"]) for p in pat["polyLine"]]
            raw = [(round(la, 7), round(lo, 7)) for la, lo in raw]
            raw = [p for i, p in enumerate(raw) if i == 0 or p != raw[i - 1]]   # drop repeated points
            pts, _ = orient(raw, bus)
            dirn = direction(t["nome"])
            s_id, e_id = t["startPoint"]["id_migracao"], t["endPoint"]["id_migracao"]
            terminal_pts[s_id].append(pts[0])
            terminal_pts[e_id].append(pts[-1])
            if pat.get("type"):
                terminal_names[e_id][pat["type"].strip()] += 2
            for key, tid in (("first", s_id), ("last", e_id)):
                n = od_ends.get((l["numero"], dirn, key))
                if n:
                    terminal_names[tid][n] += 1
            variants.append({"line": l, "t": t, "vid": vid, "pts": pts, "bus": bus, "dir": dirn,
                             "headsign": pat.get("type", "").strip()})

    # ---------------------------------------------------------------- stops
    stops: dict[str, dict] = {}
    parents: dict[str, dict] = {}

    def add_stop(sid: int, name: str, lat: float, lon: float):
        key = str(sid)
        if key in stops:
            return
        row = {"stop_id": key, "stop_code": key, "stop_name": name.strip(), "stop_lat": round(lat, 7),
               "stop_lon": round(lon, 7), "location_type": 0, "parent_station": "", "platform_code": ""}
        st = station_of(name, stations)
        if st:
            station, code = st
            parents.setdefault(station["id"], {"stop_id": station["id"], "stop_code": "", "stop_name": station["name"],
                                               "stop_lat": round(station["lat"], 7), "stop_lon": round(station["lon"], 7),
                                               "location_type": 1, "parent_station": "", "platform_code": ""})
            row.update(parent_station=station["id"], platform_code="" if code == "DESC" else code,
                       stop_name=f"{station['name']} {code}".strip() if code != "DESC" else f"{station['name']} (descenso)")
        stops[key] = row

    for v in variants:
        for b in v["bus"]:
            p = points.get(b["id"], {"latLng": b["latLng"], "name": b["name"]})
            add_stop(b["id"], p["name"], p["latLng"]["lat"], p["latLng"]["lng"])
    for tid, pts in terminal_pts.items():
        name = terminal_names[tid].most_common(1)[0][0] if terminal_names[tid] else f"Terminal {tid}"
        lat = statistics.median(p[0] for p in pts)
        lon = statistics.median(p[1] for p in pts)
        add_stop(tid, name, lat, lon)

    # ---------------------------------------------------------------- routes, shapes, trips, stop_times
    routes, shapes, trips, stop_times, attributions = [], [], [], [], []
    seen_routes = set()
    departures = {svc: {} for svc in SAMPLE_DATES}
    for v in variants:
        for svc, ds in SAMPLE_DATES.items():
            got = []
            for d in ds:
                path = M2M / "departure" / d / f"{v['vid']}.json"
                j = read_json(path) if path.exists() else []
                got.append(tuple(j[0].get("partidas", [])) if j else ())
            if len(set(got)) > 1:
                print(f"warning: {v['line']['numero']} {v['vid']} {svc} differs between {ds}", file=sys.stderr)
            departures[svc][v["vid"]] = list(got[0])

    for v in variants:
        l, t, vid = v["line"], v["t"], v["vid"]
        rid = str(l["id"])
        if rid not in seen_routes:
            seen_routes.add(rid)
            kind, colour = ROUTE_TYPES.get(l["numero"][0], ("", "666666"))
            long_name = re.sub(rf"^{re.escape(l['numero'])}\s*", "", l["name"]).strip().title()
            routes.append({"route_id": rid, "agency_id": "transcaribe", "route_short_name": l["numero"],
                           "route_long_name": long_name, "route_desc": kind, "route_type": 3,
                           "route_color": colour, "route_text_color": "FFFFFF"})
            for e in l.get("empresas", []):
                attributions.append({"attribution_id": f"{rid}_{e['id']}", "route_id": rid,
                                     "organization_name": e["nome"].strip(), "is_operator": 1})

        line = Line([xy(*p) for p in v["pts"]])
        cum = [0.0]
        for a, b in zip(line.pts, line.pts[1:]):
            cum.append(cum[-1] + ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)
        for i, (la, lo) in enumerate(v["pts"]):
            shapes.append({"shape_id": str(vid), "shape_pt_lat": round(la, 7), "shape_pt_lon": round(lo, 7),
                           "shape_pt_sequence": i, "shape_dist_traveled": round(cum[i], 1)})

        seq_stops = ([{"id": t["startPoint"]["id_migracao"], "lat": v["pts"][0][0], "lon": v["pts"][0][1]}]
                     + [{"id": b["id"], "lat": b["latLng"]["lat"], "lon": b["latLng"]["lng"]} for b in v["bus"]]
                     + [{"id": t["endPoint"]["id_migracao"], "lat": v["pts"][-1][0], "lon": v["pts"][-1][1]}])
        pos = positions(line, seq_stops)
        for i in range(1, len(pos)):                 # strictly increasing along the shape
            pos[i] = max(pos[i], pos[i - 1] + 1)

        # running time per leg: GraphHopper where it followed the line, else the line at the
        # variant's median GraphHopper speed (or FALLBACK_KMH)
        vl = legs.get(vid, {})
        ok = [r for r in vl.values() if not r["check"] and r["gh_time_s"] and float(r["gh_time_s"]) > 0
              and float(r["shape_dist_m"]) > 50]
        speed = statistics.median(float(r["gh_dist_m"]) / float(r["gh_time_s"]) for r in ok) if ok else FALLBACK_KMH / 3.6
        offsets, t_now = [], 0.0
        for i, s in enumerate(seq_stops):
            if i:
                r = vl.get(i)
                d = pos[i] - pos[i - 1]
                run = float(r["gh_time_s"]) if r and not r["check"] and r["gh_time_s"] else d / speed
                t_now += run
            arr = t_now
            st = stops[str(s["id"])]
            dwell = 0 if i in (0, len(seq_stops) - 1) else (DWELL_STATION if st["parent_station"] else DWELL_STREET)
            t_now += dwell
            offsets.append((arr, t_now))

        headsign = CODE.sub(lambda m: m["base"], v["headsign"]) if v["headsign"] else ""
        direction_id = 1 if v["dir"] == "VUELTA" else 0
        for svc in SAMPLE_DATES:
            used = Counter()
            for hhmm in departures[svc].get(vid, []):
                h, m = map(int, hhmm.split(":"))
                base = h * 3600 + m * 60
                tag = f"{h:02d}{m:02d}"
                used[tag] += 1
                trip_id = f"{vid}_{svc}_{tag}" + (f"_{used[tag]}" if used[tag] > 1 else "")
                trips.append({"route_id": rid, "service_id": svc, "trip_id": trip_id, "trip_headsign": headsign,
                              "direction_id": direction_id, "shape_id": str(vid)})
                for i, (s, (arr, dep)) in enumerate(zip(seq_stops, offsets)):
                    stop_times.append({"trip_id": trip_id, "arrival_time": hms(base + arr),
                                       "departure_time": hms(base + dep), "stop_id": str(s["id"]),
                                       "stop_sequence": i + 1, "shape_dist_traveled": round(pos[i], 1),
                                       "timepoint": 1 if i == 0 else 0})

    # ---------------------------------------------------------------- write
    write("agency.txt", [{"agency_id": "transcaribe", "agency_name": "Transcaribe",
                          "agency_url": "https://transcaribe.gov.co", "agency_timezone": "America/Bogota",
                          "agency_lang": "es"}])
    write("routes.txt", sorted(routes, key=lambda r: r["route_short_name"]))
    write("stops.txt", list(parents.values()) + sorted(stops.values(), key=lambda s: int(s["stop_id"])))
    write("shapes.txt", shapes)
    write("trips.txt", trips)
    write("stop_times.txt", stop_times)
    write("attributions.txt", attributions)
    gtfs_calendar.write(start, end, OUT)
    write("feed_info.txt", [{"feed_publisher_name": "ColombiaTransit",
                             "feed_publisher_url": "https://github.com/ColombiaTransit/gtfs-cartagena",
                             "feed_lang": "es",
                             "feed_contact_url": "https://github.com/ColombiaTransit/gtfs-cartagena/issues",
                             "feed_start_date": start.strftime("%Y%m%d"),
                             "feed_end_date": end.strftime("%Y%m%d"),
                             "feed_version": date.today().isoformat()}])

    zpath = BUILD / "transcaribe-gtfs.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(OUT.glob("*.txt")):
            z.write(f, f.name)
    print(f"{len(routes)} routes, {len(stops) + len(parents)} stops ({len(parents)} stations), "
          f"{len(variants)} shapes, {len(trips)} trips, {len(stop_times)} stop_times -> {zpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
