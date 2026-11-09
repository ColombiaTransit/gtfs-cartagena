#!/usr/bin/env python3
"""
Give every Transcaribe stop from the open data a position, using OpenStreetMap.

Inputs
    raw/transcaribe_stops.json       open data: stops per route/direction, in order
    raw/osm/overpass_stops.json      OSM bus stops, platforms and stations
    raw/osm/overpass_routes.json     OSM route relations with way geometry

Outputs
    data/shapes_osm.geojson          one round-trip line per route (from OSM)
    data/stop_positions.csv          one row per route/direction/stop with lat/lon
    data/stop_positions.geojson      the same as points, for a quick map check

Method, per route (IDA + VUELTA as one round trip, or CIRCULAR):
  1. Build the round trip from the relation's ways, pick its direction and
     rotate it so it starts at the first stop of IDA.
  2. Anchors: stops whose name matches an OSM station / named stop
     (method osm_station / osm_named), else a Photon result with a matching
     name near the line (method photon, from raw/geocode/photon.json).
     Projected onto the line, in order.
  2b. Stops identified by name on the official route map
     (data/map_labels/<route>.csv, hand-checked): method map_label.
  3a. Between two anchors, the stop markers of the official route map
     (raw/web/markers.json): paired in order when the counts match
     (map_order), otherwise by expected position (map_aligned).
  3b. Between two anchors, unnamed OSM stops on the right-hand side of the line:
     paired in order when the counts match (osm_order), otherwise matched to
     the nearest evenly-spaced expected position (osm_aligned).
  4. Everything else is spread evenly along the line between its neighbours
     (method interpolated) and needs checking.

OSM data © OpenStreetMap contributors, ODbL.
"""

from __future__ import annotations

import csv
import json

import numpy as np
import math
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / "data"

LAT0 = 10.4
KX = 111320 * math.cos(math.radians(LAT0))
KY = 110574

STATION_RADIUS = 80     # m, station centroid to line
STOP_RADIUS = 30        # m, OSM bus stop to line
CENTER_TOLERANCE = 6    # m, stops this close to the line count for either side
MIN_STEP = 25           # m, two consecutive stops are never at the same spot
REVISIT_STEP = 500      # m, before the same station can be served again


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def xy(lat: float, lon: float) -> tuple[float, float]:
    return lon * KX, lat * KY


def latlon(x: float, y: float) -> tuple[float, float]:
    return y / KY, x / KX


# ---------------------------------------------------------------- line helpers

class Line:
    def __init__(self, pts: list[tuple[float, float]]):
        self.pts = pts
        self.cum = [0.0]
        for a, b in zip(pts, pts[1:]):
            self.cum.append(self.cum[-1] + math.dist(a, b))
        self.length = self.cum[-1]

    def project(self, p):
        """All local projections: list of (pos, dist, side) per segment."""
        out = []
        for i, (a, b) in enumerate(zip(self.pts, self.pts[1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            l2 = dx * dx + dy * dy
            t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
            qx, qy = a[0] + t * dx, a[1] + t * dy
            d = math.hypot(p[0] - qx, p[1] - qy)
            cross = dx * (p[1] - a[1]) - dy * (p[0] - a[0])   # >0: left, <0: right
            out.append((self.cum[i] + t * math.sqrt(l2), d, -1 if cross < 0 else 1))
        return out

    def nearest_after(self, p, cursor, radius, right_side=False):
        best = None
        for pos, d, side in self.project(p):
            if pos < cursor - 1 or d > radius:
                continue
            if right_side and side > 0 and d > CENTER_TOLERANCE:
                continue
            # first pass after the cursor wins; within that pass the closest point
            if best is None or pos < best[0] - 200 or (abs(pos - best[0]) <= 200 and d < best[1]):
                best = (pos, d)
        return best

    def point_at(self, pos):
        pos = max(0.0, min(self.length, pos))
        for i in range(len(self.cum) - 1):
            if self.cum[i + 1] >= pos:
                a, b = self.pts[i], self.pts[i + 1]
                seg = self.cum[i + 1] - self.cum[i]
                t = 0 if seg == 0 else (pos - self.cum[i]) / seg
                return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
        return self.pts[-1]


def chain_ways(ways: list[list[tuple[int, tuple[float, float]]]]) -> list[tuple[float, float]]:
    """Join ways (lists of (node_id, xy)) into one line, flipping where needed."""
    line: list[tuple[int, tuple[float, float]]] = []
    for i, w in enumerate(ways):
        if not line:
            nxt = ways[i + 1] if i + 1 < len(ways) else None
            if nxt and w[0][0] in (nxt[0][0], nxt[-1][0]):
                w = w[::-1]
            line = list(w)
            continue
        end = line[-1][0]
        if w[-1][0] == end:
            w = w[::-1]
        elif w[0][0] != end:
            # gap: connect to whichever end is closer
            if math.dist(line[-1][1], w[-1][1]) < math.dist(line[-1][1], w[0][1]):
                w = w[::-1]
        line.extend(w[1:] if w[0][0] == end else w)
    return [p for _, p in line]


# ---------------------------------------------------------------- OSM loading

def load_osm():
    stops_raw = json.loads((RAW / "osm" / "overpass_stops.json").read_text())["elements"]
    routes_raw = json.loads((RAW / "osm" / "overpass_routes.json").read_text())["elements"]

    named: dict[str, dict] = {}     # normalised name -> {lat, lon, osm, kind}
    unnamed: list[dict] = []
    for e in stops_raw:
        t = e.get("tags", {})
        if t.get("type") in ("route", "route_master"):
            continue
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        if lat is None:
            continue
        rec = {"lat": lat, "lon": lon, "osm": f"{e['type'][0]}{e['id']}"}
        is_station = e["type"] != "node" or t.get("public_transport") == "station"
        name = t.get("name", "")
        # names like "X102" or "BUS.T103" describe routes, not places
        if name and not re.search(r"\b[ATXC]\d{3}E?\b|^bus\b", name, re.I):
            rec["kind"] = "osm_station" if is_station else "osm_named"
            key = norm(name)
            # a station beats a plain stop with the same name
            if key not in named or (is_station and named[key]["kind"] != "osm_station"):
                named[key] = rec
        elif e["type"] == "node" and (t.get("highway") == "bus_stop" or t.get("public_transport") == "platform"):
            unnamed.append(rec)

    # aliases used in the open data
    for alias, target in {
        "transferencia santa lucia": "santa lucia",
        "terminal de transportes": "terminal de transportes de cartagena",
        "delicias": "las delicias",
    }.items():
        if target in named:
            named.setdefault(alias, named[target])

    ways = {e["id"]: e for e in routes_raw if e["type"] == "way"}
    lines: dict[str, Line] = {}
    for r in routes_raw:
        if r["type"] != "relation":
            continue
        ref = r["tags"].get("ref")
        wl = []
        for m in r["members"]:
            if m["type"] == "way" and m["role"] == "" and m["ref"] in ways:
                w = ways[m["ref"]]
                wl.append([(n, xy(g["lat"], g["lon"])) for n, g in zip(w["nodes"], w["geometry"])])
        if ref and wl:
            lines[ref] = Line(chain_ways(wl))
    return named, unnamed, lines


def anchor_for(address: str, named: dict) -> dict | None:
    a = norm(address)
    a = re.sub(r" [a-d]\d$", "", a)          # vagón suffix: "madre bernarda a1"
    if a in named:
        return named[a]
    # "Patio Portal D2", "Frente a Las Américas" etc.: longest OSM name contained in the address
    return None


# ---------------------------------------------------------------- main

def main() -> int:
    named, unnamed, lines = load_osm()
    geo_path = RAW / "geocode" / "photon.json"
    geo = json.loads(geo_path.read_text()) if geo_path.exists() else {}
    maps_path = RAW / "web" / "markers.json"
    maps = json.loads(maps_path.read_text()) if maps_path.exists() else {}
    od = json.loads((RAW / "transcaribe_stops.json").read_text())

    by_route: dict[str, list[dict]] = defaultdict(list)
    for s in od:
        by_route[s["Codigo_Rutas"]].append(s)

    rows, shapes, report = [], [], []
    for route, stops in sorted(by_route.items()):
        stops.sort(key=lambda s: int(s["Gid"]))
        line = lines.get(route)
        if not line:
            report.append((route, len(stops), "no OSM line"))
            for s in stops:
                rows.append(row(route, s, None, None, "no_line", "", None))
            continue

        # orientation: OSM relations are not always drawn in the direction of IDA,
        # so try both and keep the one where more named stops line up in order
        options = []
        for cand_line in (line, Line(line.pts[::-1])):
            cand_line = rotate(cand_line, stops, named)
            p_, m_ = place_anchors(cand_line, stops, named, geo, route)
            n = len(stops)
            spread = sum(abs(x - cand_line.length * i / n) for i, x in enumerate(p_) if x is not None)
            options.append(((sum(1 for x in p_ if x is not None), -spread), cand_line, p_, m_))
        # most anchors; then anchors closest to where an even spread of stops puts them
        _, line, pos, meta = max(options, key=lambda o: o[0])

        lat_lon = [latlon(*p) for p in line.pts]
        shapes.append({"type": "Feature", "properties": {"route": route, "length_km": round(line.length / 1000, 2)},
                       "geometry": {"type": "LineString", "coordinates": [[round(lo, 6), round(la, 6)] for la, lo in lat_lon]}})

        if pos[0] is None:
            pos[0], meta[0] = 0.0, ("line_start", "", None)
        if pos[-1] is None:
            pos[-1], meta[-1] = line.length, ("line_end", "", None)

        # pass 1a: stops identified by name on the official route map (hand-checked)
        label_pass(line, stops, pos, meta, maps.get(route), route)

        # pass 1b: stop markers read off the official route map
        map_pass(line, stops, pos, meta, maps.get(route))

        # pass 2: unnamed OSM stops between anchors, paired in order when counts match
        cand = []
        for u in unnamed:
            p = xy(u["lat"], u["lon"])
            for ppos, d, side in line.project(p):
                if d <= STOP_RADIUS and (side < 0 or d <= CENTER_TOLERANCE):
                    cand.append((ppos, u, d))
        cand.sort(key=lambda c: c[0])
        used: set[str] = set()
        known = [i for i, p in enumerate(pos) if p is not None]
        for a, b in zip(known, known[1:]):
            gap = list(range(a + 1, b))
            if not gap:
                continue
            between, seen = [], set()
            for c in cand:
                if pos[a] + 15 < c[0] < pos[b] - 15 and c[1]["osm"] not in used and c[1]["osm"] not in seen:
                    seen.add(c[1]["osm"])
                    between.append(c)
            if len(between) == len(gap):
                pairs = list(zip(gap, between))
                method = "osm_order"
            else:
                pairs = align(gap, between, pos[a], pos[b])
                method = "osm_aligned"
            for i, c in pairs:
                pos[i] = c[0]
                meta[i] = (method, c[1]["osm"], round(c[2], 1))
                used.add(c[1]["osm"])

        # pass 3: interpolate the rest
        known = [i for i, p in enumerate(pos) if p is not None]
        for a, b in zip(known, known[1:]):
            n = b - a
            for j, i in enumerate(range(a + 1, b), start=1):
                pos[i] = pos[a] + (pos[b] - pos[a]) * j / n
                meta[i] = ("interpolated", "", None)

        counts = defaultdict(int)
        for i, s in enumerate(stops):
            la, lo = latlon(*line.point_at(pos[i]))
            rows.append(row(route, s, la, lo, meta[i][0], meta[i][1], meta[i][2], pos[i]))
            counts[meta[i][0]] += 1
        report.append((route, len(stops), dict(counts)))

    write_outputs(rows, shapes, named, unnamed)
    for r in report:
        print(*r)
    return 0


def rotate(line: Line, stops, named) -> Line:
    """
    Start a closed round trip at the first stop.

    If the first stop has no OSM match, use the first stop that has one and
    start the line the proportional distance (by stop count) before it.
    """
    pts = line.pts
    if math.dist(pts[0], pts[-1]) > 50:
        return line
    for i, s in enumerate(stops):
        a = anchor_for(s["Ubicacion_del_Paradero"], named)
        if a:
            break
    else:
        return line
    at = min(line.project(xy(a["lat"], a["lon"])), key=lambda t: (round(t[1] / 20), t[0]))[0]
    start = (at - line.length * i / len(stops)) % line.length
    k = max(j for j, c in enumerate(line.cum) if c <= start)
    if 0 < k < len(pts) - 1:
        return Line(pts[k:] + pts[1:k + 1])
    return line


def place_anchors(line: Line, stops, named, geo=None, route=""):
    """
    Pass 1: stops with a matching OSM name, projected onto the line in order.
    Stops without one may use a Photon result (method photon), if it lies
    close to the line, in order.
    """
    pos: list[float | None] = [None] * len(stops)
    meta: list[tuple[str, str, float | None]] = [("", "", None)] * len(stops)
    cursor = -MIN_STEP
    first_osm = None
    seen: set[str] = set()
    last_i: int | None = None
    for i, s in enumerate(stops):
        a = anchor_for(s["Ubicacion_del_Paradero"], named)
        if not a:
            hit = photon_hit(line, s, geo, route, cursor + MIN_STEP)
            if hit and last_i is not None:
                allowed = line.length * (i - last_i) / len(stops) * 3 + 2000
                if hit[0] - cursor > allowed:
                    hit = None
            if hit:
                pos[i], cursor, last_i = hit[0], hit[0], i
                meta[i] = ("photon", hit[2], round(hit[1], 1))
            continue
        if i == 0:
            first_osm = a["osm"]
        # a round trip ends where it started
        if i == len(stops) - 1 and a["osm"] == first_osm:
            pos[i], meta[i] = line.length, (a["kind"], a["osm"], None)
            break
        station = a["kind"] == "osm_station"
        # the same station in the other direction is on a later pass of the line
        step = REVISIT_STEP if a["osm"] in seen else MIN_STEP
        seen.add(a["osm"])
        hit = line.nearest_after(xy(a["lat"], a["lon"]), cursor + step,
                                 STATION_RADIUS if station else STOP_RADIUS,
                                 right_side=not station)
        # a match far beyond what the number of stops in between allows is a later
        # pass of the line (or the line takes another road): leave it out
        if hit and last_i is not None:
            allowed = line.length * (i - last_i) / len(stops) * 3 + 2000
            if hit[0] - cursor > allowed:
                hit = None
        if hit:
            pos[i], cursor, last_i = hit[0], hit[0], i
            meta[i] = (a["kind"], a["osm"], round(hit[1], 1))
    return pos, meta


STOPWORDS = {"de", "la", "el", "los", "las", "y", "del", "a", "al", "en", "con", "entre",
             "cc", "c", "mz", "lote", "kr", "cr", "cra", "carrera", "cl", "cll", "calle",
             "tv", "dg", "no", "frente", "entrada", "antes", "esquina", "sector", "etapa"}
PHOTON_RADIUS = 60      # m, Photon result to line (POIs are often set back from the road)


def tokens(text: str) -> set[str]:
    return {t for t in norm(text).split() if t not in STOPWORDS and not t.isdigit() and len(t) > 1}


def photon_hit(line, s, geo, route, cursor):
    """Best Photon result for this stop that matches its name and lies on the line."""
    if not geo:
        return None
    entry = geo.get(f"{route}|{s['Sentido']}|{int(s['Paraderos'][1:])}")
    if not entry or entry.get("name") != s["Ubicacion_del_Paradero"].strip():
        return None
    want = tokens(entry["query"])
    if not want or not any(len(t) >= 4 for t in want):
        return None
    best = None
    for r in entry["results"]:
        if r.get("osm_key") == "place" or (r.get("osm_key") == "highway" and r.get("osm_value") != "bus_stop"):
            continue
        have = tokens(" ".join(str(r.get(k, "")) for k in ("name", "street")))
        overlap = want & have
        if len(overlap) / len(want) < 0.5 or not any(len(t) >= 4 for t in overlap):
            continue
        hit = line.nearest_after(xy(r["lat"], r["lon"]), cursor, PHOTON_RADIUS)
        if hit and (best is None or hit[0] < best[0]):
            best = (hit[0], hit[1], f"{r.get('osm_type', '')}{r.get('osm_id', '')}")
    return best


LABELS = ROOT / "data" / "map_labels"
LABEL_RADIUS = 150      # m, labelled marker to line (maps may be squeezed locally)
LABEL_MAX_MEDIAN = 40   # m, map fit still usable for labelled markers
TRUSTED = ("osm_station", "osm_named", "map_label")


def label_pass(line, stops, pos, meta, info, route):
    """
    Use data/map_labels/<route>.csv: per stop the pixel of its marker on the
    official map, matched by reading the map labels. Where the map fits the
    route reasonably, its transform gives a coordinate that is projected onto
    the line in order; where it does not, stops are spread between stations
    in proportion to the distances on the map. Then anchors from other sources
    that are out of order with these are dropped.
    """
    path = LABELS / f"{route}.csv"
    if not info or not path.exists():
        return
    rows = {(r["direction"], int(r["seq"])): (float(r["px"]), float(r["py"]))
            for r in csv.DictReader(path.open(encoding="utf-8"))}
    usable = ((info.get("median_m") or 1e9) <= LABEL_MAX_MEDIAN and "transform" in info
              and (info.get("share_of_line") or 0) >= 0.3)
    if usable:
        # the map transform gives a rough coordinate; take the nearest point
        # of the line after the previous stop
        X = np.array(info["transform"])
        cursor, last_i = -MIN_STEP, 0
        fixed = [(i, pos[i]) for i, m in enumerate(meta)
                 if m[0] in ("osm_station", "osm_named") and pos[i] is not None]
        for i, s in enumerate(stops):
            if meta[i][0] in ("osm_station", "osm_named") and pos[i] is not None:
                cursor, last_i = pos[i], i
                continue
            px = rows.get((s["Sentido"], int(s["Paraderos"][1:])))
            if not px:
                continue
            mx, my = np.array([px[0], px[1], 1.0]) @ X
            hit = line.nearest_after((mx, my), cursor + MIN_STEP, LABEL_RADIUS)
            # a jump far beyond what the stops in between allow is a later pass;
            # and a stop never lies beyond the next station
            if hit and hit[0] - max(cursor, 0) > line.length * (i - last_i) / len(stops) * 3 + 1000:
                hit = None
            nxt = [p for j, p in fixed if j > i]
            if hit and nxt and hit[0] >= min(nxt):
                hit = None
            if hit:
                pos[i], cursor, last_i = hit[0], hit[0], i
                meta[i] = ("map_label", f"map:{int(px[0])},{int(px[1])}", round(hit[1], 1))
    # labelled stops still without a place (no transform, or too far from the
    # line): spread them between the known stops around them in proportion to
    # the distances between their markers on the map
    known = [i for i, m in enumerate(meta)
             if pos[i] is not None and m[0] in ("osm_station", "osm_named", "map_label")]
    ends = ([0] if 0 not in known else []) + known + ([len(stops) - 1] if len(stops) - 1 not in known else [])
    key = lambda i: (stops[i]["Sentido"], int(stops[i]["Paraderos"][1:]))
    for a, b in zip(ends, ends[1:]):
        gap = [i for i in range(a + 1, b) if key(i) in rows]
        if not gap:
            continue
        pa = pos[a] if pos[a] is not None and meta[a][0] in ("osm_station", "osm_named", "map_label") else (0.0 if a == 0 else None)
        pb = pos[b] if pos[b] is not None and meta[b][0] in ("osm_station", "osm_named", "map_label") else (line.length if b == len(stops) - 1 else None)
        if pa is None or pb is None:
            continue
        # include the neighbours' own markers, when labelled, as the ends of the chain
        P = [rows[key(i)] for i in gap]
        steps = [math.dist(p, q) for p, q in zip(P, P[1:])]
        edge = (sum(steps) / len(steps)) if steps else 1.0
        first = math.dist(rows[key(a)], P[0]) if key(a) in rows else edge
        last = math.dist(P[-1], rows[key(b)]) if key(b) in rows else edge
        cum = [first]
        for d in steps:
            cum.append(cum[-1] + d)
        total = cum[-1] + last
        for i, c, p in zip(gap, cum, P):
            pos[i] = pa + (pb - pa) * c / total
            meta[i] = ("map_label", f"map:{int(p[0])},{int(p[1])}", None)

    # anchors from other sources that contradict the labelled order go
    trusted = [i for i, m in enumerate(meta) if m[0] in TRUSTED and pos[i] is not None]
    for i, m in enumerate(meta):
        if pos[i] is None or m[0] in TRUSTED or i in (0, len(stops) - 1):
            continue
        before = [pos[j] for j in trusted if j < i]
        after = [pos[j] for j in trusted if j > i]
        if (before and pos[i] < max(before)) or (after and pos[i] > min(after)):
            pos[i], meta[i] = None, ("", "", None)


MAP_RADIUS = 60         # m, georeferenced marker to line
MAP_SAME_STOP = 120     # m, a marker this close to an anchor is that anchor's stop


def map_pass(line, stops, pos, meta, info):
    """
    Run the map pass with both ways of choosing the direction of a marker on a
    shared road and keep whichever places more stops (on some maps the colour
    offset is too small for the side of the road to be reliable).
    """
    best = None
    for strategy in ("side", "half"):
        p_, m_ = list(pos), list(meta)
        _map_pass(line, stops, p_, m_, info, strategy)
        filled = sum(1 for a, b in zip(meta, m_) if a != b)
        if best is None or filled > best[0]:
            best = (filled, p_, m_)
    pos[:], meta[:] = best[1], best[2]


def _map_pass(line, stops, pos, meta, info, strategy):
    """
    Fill the gaps between anchors with the markers of the official route map
    (raw/web/markers.json, made by scripts/georef_maps.py).

    Each colour on the map is one direction. Where both directions use the
    same road a marker projects onto both passes of the round trip; it takes
    the pass on which it lies on its colour's side of the road (learnt from
    the markers that project onto only one pass).
    """
    if not info or not info.get("ok"):
        return
    markers = info["markers"]
    n_free = sum(1 for m in meta if m[0] in ("", "line_start", "line_end"))
    # a map whose marker count is far off is read wrongly (or shows another variant)
    if not markers or not 0.75 * n_free <= len(markers) <= 1.25 * n_free + 2:
        return
    n_ida = sum(1 for s in stops if s["Sentido"] == "IDA")
    turn = line.length * n_ida / len(stops) if n_ida < len(stops) else None

    projected = []
    for m in markers:
        c = sorted(((p, d, side) for p, d, side in line.project(xy(m["lat"], m["lon"])) if d <= MAP_RADIUS),
                   key=lambda t: t[1])
        passes = []
        for p, d, side in c:
            if all(abs(p - q[0]) > 200 for q in passes):
                passes.append((p, d, side))
        if passes:
            projected.append((m, passes))

    # The map draws each direction as its own line, offset to one side of the
    # road, with its markers next to it. So per colour the markers sit on a
    # fixed side of their direction of travel. Learn that side from markers
    # with only one possible pass, then use it where both directions share a road.
    side_votes: dict[str, int] = {}
    half_votes: dict[str, list[int]] = {}
    for m, passes in projected:
        if len(passes) == 1:
            side_votes[m["colour"]] = side_votes.get(m["colour"], 0) + passes[0][2]
            if turn is not None:
                half_votes.setdefault(m["colour"], [0, 0])[0 if passes[0][0] < turn else 1] += 1

    cand = []
    for m, passes in projected:
        pick = passes[0]
        if len(passes) > 1 and strategy == "half" and m["colour"] in half_votes:
            out = half_votes[m["colour"]][0] >= half_votes[m["colour"]][1]
            pick = next((t for t in passes if (t[0] < turn) == out), passes[0])
        elif len(passes) > 1:
            side = side_votes.get(m["colour"], 0)
            same_side = [t for t in passes if side and (t[2] > 0) == (side > 0)]
            if len(same_side) == 1:
                pick = same_side[0]
            elif m["colour"] in half_votes:
                out = half_votes[m["colour"]][0] >= half_votes[m["colour"]][1]
                pick = next((t for t in passes if (t[0] < turn) == out), passes[0])
        cand.append((pick[0], {"osm": f"map:{m['px'][0]},{m['px'][1]}"}, pick[1]))
    cand.sort(key=lambda c: c[0])

    known = [i for i, p in enumerate(pos) if p is not None]
    # markers at an anchor belong to that anchor's stop
    taken = set()
    for i in known:
        near = [k for k, c in enumerate(cand) if k not in taken and abs(c[0] - pos[i]) <= MAP_SAME_STOP]
        if near:
            taken.add(min(near, key=lambda k: abs(cand[k][0] - pos[i])))
    free = [c for k, c in enumerate(cand) if k not in taken]

    for a, b in zip(known, known[1:]):
        gap = list(range(a + 1, b))
        between = [c for c in free if pos[a] < c[0] < pos[b]]
        if not gap or not between:
            continue
        if len(between) == len(gap):
            pairs, method = list(zip(gap, between)), "map_order"
        else:
            pairs, method = align(gap, between, pos[a], pos[b]), "map_aligned"
        for i, c in pairs:
            pos[i] = c[0]
            meta[i] = (method, c[1]["osm"], round(c[2], 1))


def align(gap, between, start, end):
    """
    Order-preserving match of OSM candidates to stops when the counts differ.

    Stops are assumed evenly spaced between the two anchors; a candidate may
    only take a stop whose expected position is within 40% of the spacing.
    Dynamic programming minimises total offset; unmatched stops and candidates
    are free to skip.
    """
    n, m = len(gap), len(between)
    if not n or not m:
        return []
    spacing = (end - start) / (n + 1)
    expected = [start + spacing * (j + 1) for j in range(n)]
    limit = 0.4 * spacing
    INF = float("inf")
    # cost[j][k]: best (negative count, offset) using first j stops and k candidates
    best = [[(0, 0.0)] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    for j in range(n + 1):
        for k in range(m + 1):
            if j == 0 and k == 0:
                continue
            opts = []
            if j > 0:
                opts.append((best[j - 1][k], "skip_stop"))
            if k > 0:
                opts.append((best[j][k - 1], "skip_cand"))
            if j > 0 and k > 0:
                off = abs(between[k - 1][0] - expected[j - 1])
                if off <= limit:
                    c, o = best[j - 1][k - 1]
                    opts.append(((c - 1, o + off), "match"))
            choice = min(opts, key=lambda t: t[0]) if opts else ((0, INF), None)
            best[j][k], back[j][k] = choice
    pairs, j, k = [], n, m
    while j > 0 or k > 0:
        step = back[j][k]
        if step == "match":
            pairs.append((gap[j - 1], between[k - 1]))
            j, k = j - 1, k - 1
        elif step == "skip_stop":
            j -= 1
        else:
            k -= 1
    return pairs[::-1]


def row(route, s, lat, lon, method, osm, dist, pos=None):
    return {
        "route": route,
        "direction": s["Sentido"],
        "seq": int(s["Paraderos"][1:]),
        "paradero": s["Paraderos"],
        "name": s["Ubicacion_del_Paradero"].strip(),
        "lat": None if lat is None else round(lat, 6),
        "lon": None if lon is None else round(lon, 6),
        "method": method,
        "osm_id": osm,
        "osm_dist_m": dist,
        "pos_m": None if pos is None else round(pos),
    }


def write_outputs(rows, shapes, named, unnamed):
    OUT.mkdir(exist_ok=True)
    # use the OSM coordinate itself for matched stops
    lookup = {r["osm"]: r for r in list(named.values()) + unnamed}
    for r in rows:
        if r["osm_id"] in lookup and r["method"] in ("osm_named", "osm_order", "osm_aligned"):
            r["lat"], r["lon"] = lookup[r["osm_id"]]["lat"], lookup[r["osm_id"]]["lon"]

    with (OUT / "stop_positions.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    colors = {"osm_station": "#1a7f37", "osm_named": "#1a7f37", "osm_order": "#0969da", "osm_aligned": "#8250df", "photon": "#bc4c00", "map_order": "#1f6feb", "map_aligned": "#6639ba", "map_label": "#0a3069",
              "interpolated": "#cf222e", "line_start": "#bf8700", "line_end": "#bf8700"}
    feats = [{"type": "Feature",
              "properties": {**{k: v for k, v in r.items() if k not in ("lat", "lon")},
                             "marker-color": colors.get(r["method"], "#6e7781"), "marker-size": "small"},
              "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]}}
             for r in rows if r["lat"] is not None]
    (OUT / "stop_positions.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
    (OUT / "shapes_osm.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": shapes}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
