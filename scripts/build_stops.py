#!/usr/bin/env python3
"""
Build the GTFS stops from data/stop_positions.csv (one row per route,
direction and stop): merge the stops that several routes serve, and model the
trunk stations with their vagones. Issue #24.

Inputs
    data/stop_positions.csv          positions per route/direction/stop
    raw/osm/overpass_stations.json   stations, platforms (vagones), stop areas

Outputs
    data/stops.csv       GTFS stops.txt columns plus `quality` (how the position
                         was found) and `routes` (which routes stop there)
    data/stop_ids.csv    route, direction, seq -> stop_id, for trips/stop_times
    data/stops_review.csv  merged stops to check by hand: rows with different
                         names, or route positions more than REVIEW_M apart

Stations. Stop names ending in a vagón code ("Madre Bernarda B1", "Patio
Portal D2") are platforms of a trunk station: the station becomes
location_type=1 and every code a platform (location_type=0, parent_station,
platform_code). The letter is the vagón, the digit the side: 1 towards the
centre (IDA), 2 back (VUELTA); at Patio Portal the codes are bays. A vagón is
placed on its part of the OSM platform: on two-vagón stations OSM has two
parts, and vagón A is taken to be the one nearer Patio Portal (an assumption,
to check). Both sides of a vagón share its position.

Street stops. Rows are the same stop when they have the same name (as in
match_stops.shared_key, so "Clinica El Bosque V" = "Clínica El Bosque") and lie
within MERGE_M of each other with a similar heading (the bus goes the same
way), or when they lie within SAME_SPOT_M with a similar heading whatever their
names, if one of them is an address such as "Kr 1 entre Cl 43 y 44" (else
within SAME_POINT_M). A stop never holds two stops of one route (that would chain neighbouring
stops together), and the closest pairs are joined first. The stop takes the position of its best-placed rows (see QUALITY),
their median when there are several.
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import match_stops as m  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OSM = ROOT / "raw" / "osm"

MERGE_M = 300          # same name, same direction: one stop when this close
SAME_SPOT_M = 25       # different names, same direction: one stop when this close, if one name is an address
SAME_POINT_M = 8       # different names, same direction: one stop when this close anyway
ADDRESS = re.compile(r"\b(entre|kr|cr|cra|carrera|cl|cll|calle|tv|transversal|dg|diagonal|mz)\b|#", re.I)
HEADING_DEG = 60       # "same direction"
PORTAL = (10.3956156, -75.4726545)
REVIEW_M = 150         # merged rows further apart than this are listed for review

# lower is better; the stop's position comes from its best rows
QUALITY = {
    "osm_station": 0, "osm_named": 0, "osm_order": 1, "osm_poi": 1,
    "map_georef": 2, "map_label": 2, "map_order": 2, "photon": 2, "shared_stop": 3,
    "osm_aligned": 4, "map_aligned": 4, "shared_estimate": 5,
    "interpolated": 6, "line_start": 6, "line_end": 6,
}
VAGON = re.compile(r"^(?P<station>.*?)\s+(?P<code>[A-F]\d)$")
DIRECTION_WORDS = {"vuelta", "ida", "v"}
STATION_ALIASES = {"delicias": "las delicias", "los angeles": "los angeles", "chambacu": "chambacu",
                   "transferencia santa lucia": "santa lucia"}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", m.norm(text)).strip("_")


def key_of(name: str) -> str:
    k = m.shared_key(name)
    return " ".join(t for t in k.split() if t not in DIRECTION_WORDS)


def bearing(a, b) -> float | None:
    dx, dy = (b[1] - a[1]) * m.KX, (b[0] - a[0]) * m.KY
    if math.hypot(dx, dy) < 1:
        return None
    return math.degrees(math.atan2(dx, dy)) % 360


def same_way(h1, h2) -> bool:
    if h1 is None or h2 is None:
        return True
    d = abs(h1 - h2) % 360
    return min(d, 360 - d) <= HEADING_DEG


def dist(a, b) -> float:
    return math.hypot((a[0] - b[0]) * m.KY, (a[1] - b[1]) * m.KX)


def load_osm_stations() -> dict[str, dict]:
    """Normalised station name -> {lat, lon, parts: [(lat, lon), ...], osm}."""
    path = OSM / "overpass_stations.json"
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for e in json.loads(path.read_text())["elements"]:
        t = e.get("tags", {})
        name = t.get("name")
        if not name or t.get("public_transport") not in ("station", "platform"):
            continue
        parts = []
        if e["type"] == "relation":
            for mem in e.get("members", []):
                g = mem.get("geometry") or []
                if mem["type"] == "way" and mem.get("role") == "outer" and g:
                    parts.append((sum(p["lat"] for p in g) / len(g), sum(p["lon"] for p in g) / len(g)))
        elif e["type"] == "way":
            g = e.get("geometry") or []
            if g:
                parts.append((sum(p["lat"] for p in g) / len(g), sum(p["lon"] for p in g) / len(g)))
        else:
            parts.append((e["lat"], e["lon"]))
        if not parts:
            continue
        key = m.norm(name)
        if key in out and out[key]["kind"] == "station" and t.get("public_transport") != "station":
            continue
        out[key] = {"lat": sum(p[0] for p in parts) / len(parts), "lon": sum(p[1] for p in parts) / len(parts),
                    "parts": parts, "osm": f"{e['type'][0]}{e['id']}", "kind": t.get("public_transport"),
                    "name": name}
    return out


def main() -> int:
    rows = list(csv.DictReader((DATA / "stop_positions.csv").open(encoding="utf-8")))
    for r in rows:
        r["pt"] = (float(r["lat"]), float(r["lon"])) if r["lat"] else None
    # heading of the bus at each stop, from the neighbouring stops of the same route
    by_route = defaultdict(list)
    for r in rows:
        by_route[r["route"]].append(r)
    for rr in by_route.values():
        pts = [r["pt"] for r in rr]
        for i, r in enumerate(rr):
            prev = next((pts[j] for j in range(i - 1, -1, -1) if pts[j] and r["pt"] and dist(pts[j], r["pt"]) > 20), None)
            nxt = next((pts[j] for j in range(i + 1, len(rr)) if pts[j] and r["pt"] and dist(pts[j], r["pt"]) > 20), None)
            r["heading"] = bearing(prev or r["pt"], nxt or r["pt"]) if r["pt"] and (prev or nxt) else None

    osm_st = load_osm_stations()
    stops: list[dict] = []          # GTFS rows
    stop_of: dict[int, str] = {}    # row index -> stop_id
    used_ids: set[str] = set()

    def new_id(base: str) -> str:
        sid, n = base, 2
        while sid in used_ids:
            sid, n = f"{base}_{n}", n + 1
        used_ids.add(sid)
        return sid

    # ---- stations and their platforms
    station_rows = defaultdict(lambda: defaultdict(list))   # station name -> code -> row indexes
    known = {VAGON.match(r["name"].strip())["station"] for r in rows
             if r["method"] == "osm_station" and VAGON.match(r["name"].strip())}
    for i, r in enumerate(rows):
        mt = VAGON.match(r["name"].strip())
        if mt and mt["station"] in known:            # also when this route placed it otherwise
            station_rows[mt["station"]][mt["code"]].append(i)
        elif r["method"] == "osm_station" and STATION_ALIASES.get(m.norm(r["name"]), m.norm(r["name"])) in osm_st:
            station_rows[r["name"].strip()][""].append(i)   # Transcaribe station without a code
    for st_name, codes in sorted(station_rows.items()):
        key = m.norm(st_name)
        osm = osm_st.get(STATION_ALIASES.get(key, key)) or osm_st.get(key)
        members = [rows[i] for idx in codes.values() for i in idx]
        if osm:
            st_pt = (osm["lat"], osm["lon"])
        else:
            st_pt = tuple(sorted(r["pt"][k] for r in members)[len(members) // 2] for k in (0, 1))
        sid = new_id("st_" + slug(st_name))
        label = osm["name"] if osm else st_name          # OSM has the accents: Chambacú, Los Ángeles
        routes = sorted({r["route"] for r in members})
        stops.append({"stop_id": sid, "stop_code": "", "stop_name": label, "stop_lat": st_pt[0],
                      "stop_lon": st_pt[1], "location_type": 1, "parent_station": "", "platform_code": "",
                      "quality": "osm_station" if osm else "estimate", "routes": " ".join(routes)})
        # vagones: OSM parts sorted from Patio Portal outwards -> A, B, ...
        parts = sorted(osm["parts"], key=lambda p: dist(p, PORTAL)) if osm else []
        letters = sorted({c[0] for c in codes if c})
        for code, idx in sorted(codes.items()):
            if code and len(parts) >= len(letters) > 1 and st_name != "Patio Portal":
                pt = parts[letters.index(code[0])]
                quality = "osm_platform_assumed_order"
            else:
                pt, quality = st_pt, "station_centre"
            pid = new_id(f"{sid}_{code.lower()}" if code else f"{sid}_p")
            stops.append({"stop_id": pid, "stop_code": "", "stop_name": f"{label} {code}".strip(),
                          "stop_lat": pt[0], "stop_lon": pt[1], "location_type": 0, "parent_station": sid,
                          "platform_code": code, "quality": quality,
                          "routes": " ".join(sorted({rows[i]["route"] for i in idx}))})
            for i in idx:
                stop_of[i] = pid

    # ---- street stops: union-find on name + distance + heading
    street = [i for i, r in enumerate(rows) if i not in stop_of and r["pt"]]
    parent = {i: i for i in street}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    keys = {i: key_of(rows[i]["name"]) for i in street}
    pairs = []
    for a_i, a in enumerate(street):
        ra = rows[a]
        for b in street[a_i + 1:]:
            rb = rows[b]
            if ra["route"] == rb["route"]:
                continue
            d = dist(ra["pt"], rb["pt"])
            if d > MERGE_M or not same_way(ra["heading"], rb["heading"]):
                continue
            named = bool(keys[a]) and keys[a] == keys[b]
            address = bool(ADDRESS.search(ra["name"]) or ADDRESS.search(rb["name"]))
            if named or d <= (SAME_SPOT_M if address else SAME_POINT_M):
                pairs.append((not named, d, a, b))     # same name first, then the closest
    routes_in = {i: {rows[i]["route"]} for i in street}
    for _, _, a, b in sorted(pairs):
        ra, rb = find(a), find(b)
        if ra == rb or routes_in[ra] & routes_in[rb]:
            continue
        parent[ra] = rb
        routes_in[rb] |= routes_in.pop(ra)
    groups = defaultdict(list)
    for i in street:
        groups[find(i)].append(i)

    for idx in sorted(groups.values(), key=lambda g: (rows[g[0]]["route"], int(rows[g[0]]["seq"]))):
        members = [rows[i] for i in idx]
        best = min(QUALITY.get(r["method"], 9) for r in members)
        top = [r for r in members if QUALITY.get(r["method"], 9) == best]
        lat = sorted(r["pt"][0] for r in top)[len(top) // 2]
        lon = sorted(r["pt"][1] for r in top)[len(top) // 2]
        names = Counter(r["name"].strip() for r in members)
        name = max(names, key=lambda n: (names[n], not re.search(r"\b(V|Vuelta)$", n), -len(n)))
        sid = new_id(slug(name)[:40] or "stop")
        stops.append({"stop_id": sid, "stop_code": "", "stop_name": name, "stop_lat": lat, "stop_lon": lon,
                      "location_type": 0, "parent_station": "", "platform_code": "",
                      "quality": top[0]["method"], "routes": " ".join(sorted({r["route"] for r in members}))})
        for i in idx:
            stop_of[i] = sid

    missing = [rows[i] for i in range(len(rows)) if i not in stop_of]
    for s in stops:
        s["stop_lat"], s["stop_lon"] = round(s["stop_lat"], 7), round(s["stop_lon"], 7)
    with (DATA / "stops.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(stops[0]))
        w.writeheader()
        w.writerows(stops)
    with (DATA / "stop_ids.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["route", "direction", "seq", "name", "stop_id"])
        for i, r in enumerate(rows):
            w.writerow([r["route"], r["direction"], r["seq"], r["name"], stop_of.get(i, "")])

    members = defaultdict(list)
    for i, r in enumerate(rows):
        members[stop_of.get(i, "")].append(r)
    review = []
    for s in stops:
        mem = members.get(s["stop_id"], [])
        if s["parent_station"] or s["location_type"] == 1 or len(mem) < 2:
            continue
        names = sorted({r["name"].strip() for r in mem})
        spread = max(dist(a["pt"], b["pt"]) for a in mem for b in mem)
        if len({n.lower() for n in names}) > 1 or spread > REVIEW_M:
            review.append({"stop_id": s["stop_id"], "stop_name": s["stop_name"], "spread_m": round(spread),
                           "names": " | ".join(names),
                           "rows": " ".join(f"{r['route']}:{r['direction']}:{r['seq']}({r['method']})" for r in mem)})
    review.sort(key=lambda x: -x["spread_m"])
    with (DATA / "stops_review.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["stop_id", "stop_name", "spread_m", "names", "rows"])
        w.writeheader()
        w.writerows(review)

    n_st = sum(1 for s in stops if s["location_type"] == 1)
    n_pl = sum(1 for s in stops if s["parent_station"])
    print(f"{len(rows)} route stops -> {len(stops)} stops: {n_st} stations, {n_pl} platforms, "
          f"{len(stops) - n_st - n_pl} street stops; {len(missing)} without a position; "
          f"{len(review)} merged stops to review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
