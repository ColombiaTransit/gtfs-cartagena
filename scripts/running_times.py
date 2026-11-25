#!/usr/bin/env python3
"""
Running times between consecutive stops, from our GraphHopper server with the
bus profile, along the route geometry of the API snapshot (raw/m2m/). Issue #25.

Per route variant:
  1. The geometry (pattern/<line id>.json) is turned the right way round (the
     API delivers some against the direction of travel: A102 IDA) by checking
     where the first and the last stop of bustop/<variant>.json lie on it.
  2. The stops are the variant's start point, the stops of bustop/ in order,
     and the end point. Start and end points are not in allPoints.json; they
     take the first and last point of the geometry.
  3. Every stop is projected onto the geometry, in order.
  4. Every pair of consecutive stops is routed with GraphHopper from the one
     projection to the next, through via points on the geometry every VIA_M
     metres (pass_through, so no U-turns), so the route follows the bus line.

Writes data/running_times.csv: variant, seq, from/to stop, distance along the
geometry, GraphHopper distance and time, and a check flag where the two
distances differ by more than DIST_TOLERANCE (GraphHopper took another road).
Dwell times are not included; the feed builder adds them.

GRAPHHOPPER_URL: base URL of the server, without /route.

Usage: GRAPHHOPPER_URL=... python scripts/running_times.py [--profile bus] [VARIANT ...]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from match_stops import Line, latlon, xy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
M2M = ROOT / "raw" / "m2m"
OUT = ROOT / "data" / "running_times.csv"
EXCLUDE = ("A000",)
VIA_M = 300              # via point every this many metres along the geometry
MAX_VIA = 20
DIST_TOLERANCE = 0.25    # flag when GraphHopper's distance differs this much from the geometry
SNAP_RADIUS = 150        # m, stop to geometry
PAUSE = 0.05
USER_AGENT = "ColombiaTransit-gtfs-cartagena/1.0 (+https://github.com/ColombiaTransit/gtfs-cartagena)"


def load_variants(only: set[int] | None):
    lines = json.loads((M2M / "allLines.json").read_text(encoding="utf-8"))
    for line in lines:
        if str(line.get("numero", "")).startswith(EXCLUDE):
            continue
        pattern_path = M2M / "pattern" / f"{line['id']}.json"
        patterns = {p["id"]: p for p in json.loads(pattern_path.read_text())} if pattern_path.exists() else {}
        for t in line["trajetos"]:
            vid = t["id_migracao"]
            if only and vid not in only:
                continue
            bus = json.loads((M2M / "bustop" / f"{vid}.json").read_text(encoding="utf-8"))
            yield line, t, patterns.get(vid), bus


def orient(pts: list[tuple[float, float]], bus: list[dict]) -> tuple[list[tuple[float, float]], bool]:
    """Turn the geometry so the stops lie on it in increasing order."""
    if len(bus) < 2:
        return pts, False
    line = Line([xy(*p) for p in pts])
    first = min(line.project(xy(bus[0]["latLng"]["lat"], bus[0]["latLng"]["lng"])), key=lambda t: t[1])[0]
    last = min(line.project(xy(bus[-1]["latLng"]["lat"], bus[-1]["latLng"]["lng"])), key=lambda t: t[1])[0]
    if first > last:
        return pts[::-1], True
    return pts, False


def positions(line: Line, stops: list[dict]) -> list[float]:
    """Position of every stop along the line, in order (start 0, end length)."""
    pos = [0.0]
    cursor = 0.0
    for s in stops[1:-1]:
        p = xy(s["lat"], s["lon"])
        hit = line.nearest_after(p, cursor, SNAP_RADIUS)
        if not hit:                                    # off the line: nearest point after the cursor
            cands = [t for t in line.project(p) if t[0] >= cursor]
            hit = min(cands, key=lambda t: t[1]) if cands else (cursor, None)
        cursor = max(cursor, hit[0])
        pos.append(cursor)
    pos.append(line.length)
    return pos


def via_points(line: Line, a: float, b: float) -> list[tuple[float, float]]:
    n = min(MAX_VIA, int((b - a) // VIA_M))
    return [latlon(*line.point_at(a + (b - a) * k / (n + 1))) for k in range(1, n + 1)]


class GraphHopper:
    def __init__(self, base: str, profile: str):
        self.base = base.rstrip("/")
        self.profile = profile
        self.pass_through = True
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def route(self, pts: list[tuple[float, float]]) -> tuple[float | None, float | None, str]:
        params = [("point", f"{la:.6f},{lo:.6f}") for la, lo in pts]
        params += [("profile", self.profile), ("calc_points", "false"), ("instructions", "false")]
        if self.pass_through:
            params.append(("pass_through", "true"))
        for attempt in range(3):
            try:
                r = self.session.get(f"{self.base}/route", params=params, timeout=60)
            except requests.RequestException as e:
                err = type(e).__name__
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 400 and self.pass_through and "pass_through" in r.text:
                self.pass_through = False                 # CH-only server: without pass_through
                return self.route(pts)
            if r.status_code == 200:
                path = r.json()["paths"][0]
                time.sleep(PAUSE)
                return path["distance"], path["time"] / 1000.0, "ok"
            err = f"http {r.status_code}: {r.text[:120]}"
            if r.status_code < 500:
                break
            time.sleep(2 * (attempt + 1))
        return None, None, err


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="bus")
    ap.add_argument("variants", nargs="*", type=int)
    args = ap.parse_args()
    base = os.environ.get("GRAPHHOPPER_URL", "").strip()
    if not base:
        sys.exit("GRAPHHOPPER_URL is not set")
    gh = GraphHopper(base, args.profile)

    try:
        info = gh.session.get(f"{gh.base}/info", timeout=30).json()
        names = [p.get("name") or p.get("profile_name") for p in info.get("profiles", [])]
        print("profiles on the server:", ", ".join(map(str, names)))
        if names and args.profile not in names:
            sys.exit(f"profile {args.profile!r} not on the server")
    except (requests.RequestException, ValueError) as e:
        print(f"/info not readable ({type(e).__name__}), going on", file=sys.stderr)

    rows, problems = [], []
    for line, t, pattern, bus in load_variants(set(args.variants) or None):
        vid = t["id_migracao"]
        if not pattern or len(pattern.get("polyLine", [])) < 2:
            problems.append(f"{line['numero']} {vid}: no geometry")
            continue
        pts, flipped = orient([(p["lat"], p["lng"]) for p in pattern["polyLine"]], bus)
        line_m = Line([xy(*p) for p in pts])
        stops = ([{"id": t["startPoint"]["id_migracao"], "name": "(start)", "lat": pts[0][0], "lon": pts[0][1]}]
                 + [{"id": b["id"], "name": b["name"], "lat": b["latLng"]["lat"], "lon": b["latLng"]["lng"]} for b in bus]
                 + [{"id": t["endPoint"]["id_migracao"], "name": "(end)", "lat": pts[-1][0], "lon": pts[-1][1]}])
        pos = positions(line_m, stops)
        total_t = 0.0
        for i in range(len(stops) - 1):
            a, b = pos[i], pos[i + 1]
            pa, pb = latlon(*line_m.point_at(a)), latlon(*line_m.point_at(b))
            shape_d = b - a
            if shape_d < 1:
                gh_d, gh_t, status = 0.0, 0.0, "same_point"
            else:
                gh_d, gh_t, status = gh.route([pa, *via_points(line_m, a, b), pb])
            check = ""
            if gh_d is not None and shape_d > 50 and abs(gh_d - shape_d) / shape_d > DIST_TOLERANCE:
                check = "distance"
            if status not in ("ok", "same_point"):
                check = "error"
            total_t += gh_t or 0
            rows.append({"variant": vid, "route": line["numero"], "seq": i + 1,
                         "from_stop": stops[i]["id"], "to_stop": stops[i + 1]["id"],
                         "from_name": stops[i]["name"], "to_name": stops[i + 1]["name"],
                         "shape_dist_m": round(shape_d), "gh_dist_m": None if gh_d is None else round(gh_d),
                         "gh_time_s": None if gh_t is None else round(gh_t, 1), "status": status, "check": check})
        n_check = sum(1 for r in rows if r["variant"] == vid and r["check"])
        print(f"{line['numero']:6} {vid} {'flipped ' if flipped else ''}{len(stops)} stops, "
              f"{line_m.length / 1000:.1f} km (kmTrajeto {t.get('kmTrajeto')}), {total_t / 60:.1f} min driving"
              f"{f', {n_check} to check' if n_check else ''}")

    if not rows:
        sys.exit("no running times")
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    errors = sum(1 for r in rows if r["check"] == "error")
    print(f"{len(rows)} legs, {errors} errors, {sum(1 for r in rows if r['check'] == 'distance')} distance checks")
    for p in problems:
        print("problem:", p)
    return 1 if errors > len(rows) // 10 else 0


if __name__ == "__main__":
    sys.exit(main())
