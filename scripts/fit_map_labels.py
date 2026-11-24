#!/usr/bin/env python3
"""
Georeference an official route map from its labelled stops, for routes whose
OSM line is missing or wrong (so georef_maps.py cannot fit the map onto it).

Control points: labelled stops (data/map_labels/<route>.csv) whose name is the
name of a well-placed stop of another route (OSM station, OSM stop, map label,
map marker or Photon). A name can have several candidates (the same stop placed
by several routes, or the same name elsewhere in the city); the fit picks the
candidate nearest to where the current transform puts the marker, starts from
the median of the candidates, and drops outliers.

Fits a similarity transform (scale, rotation, shift) from pixels to metres and
writes data/map_labels/transforms.json, which scripts/match_stops.py uses to
place every labelled stop of the route at its map position (method map_georef),
instead of on the OSM line.

Optionally the fit is refined with the OSM route lines the map follows
(ROUTE=LINE[+LINE...]): each labelled marker within SNAP_M of one of those
lines after the fit is pulled to the nearest point of the line, and the fit
is redone with these points added, until it settles. This ties down maps whose
control points all lie in one corner (C017: only the stops shared with T102).

Usage: python scripts/fit_map_labels.py ROUTE[=LINE+LINE] [...]
       e.g. fit_map_labels.py C017=C017 A118=C016+A101+A117+A114+X104
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import match_stops as m  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "data" / "map_labels"
OUT = LABELS / "transforms.json"
GOOD = ("osm_station", "osm_named", "osm_order", "map_label", "map_order", "photon")
MAX_CANDIDATE_M = 600      # a candidate further than this from the median is another place
MAX_RESIDUAL_M = 120       # control points further off than this after the fit are dropped
SNAP_M = 400               # labelled markers this close to a given OSM line help the fit


def similarity(P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """Least-squares similarity P (px) -> Q (m) as a 3x2 matrix for [px, py, 1] @ X."""
    # the image y axis points down, so the map is mirrored relative to x/y metres:
    #   mx = a*px + b*py + tx,   my = b*px - a*py + ty
    # (same form as the transforms in raw/web/markers.json)
    n = len(P)
    A = np.zeros((2 * n, 4))
    A[:n] = np.c_[P[:, 0], P[:, 1], np.ones(n), np.zeros(n)]
    A[n:] = np.c_[-P[:, 1], P[:, 0], np.zeros(n), np.ones(n)]
    a, b, tx, ty = np.linalg.lstsq(A, np.r_[Q[:, 0], Q[:, 1]], rcond=None)[0]
    return np.array([[a, b], [b, -a], [tx, ty]])


def fit_route(route: str, rows: list[dict], line_refs: list[str] | None = None) -> dict:
    cand: dict[str, list[tuple[float, float, str]]] = {}
    for r in rows:
        if r["route"] == route or r["method"] not in GOOD or not r["lat"]:
            continue
        cand.setdefault(m.shared_key(r["name"]), []).append(
            (*m.xy(float(r["lat"]), float(r["lon"])), f"{r['route']}:{r['direction']}:{r['seq']}"))

    pts = []
    for lab in csv.DictReader((LABELS / f"{route}.csv").open(encoding="utf-8")):
        c = cand.get(m.shared_key(lab["map_label"]))
        if not c:
            continue
        med = np.median(np.array([(x, y) for x, y, _ in c]), axis=0)
        c = [t for t in c if math.dist(t[:2], med) <= MAX_CANDIDATE_M] or c
        pts.append({"label": lab["map_label"], "px": (float(lab["px"]), float(lab["py"])),
                    "cands": c, "med": tuple(np.median(np.array([(x, y) for x, y, _ in c]), axis=0))})
    if len(pts) < 3:
        return {"ok": False, "reason": f"only {len(pts)} control points"}

    P = np.array([p["px"] for p in pts])
    Q = np.array([p["med"] for p in pts])
    use = np.ones(len(pts), bool)
    X = similarity(P, Q)
    for _ in range(10):
        pred = np.c_[P, np.ones(len(P))] @ X
        # nearest candidate to the predicted position
        Q = np.array([min(p["cands"], key=lambda t: math.dist(t[:2], pr))[:2] for p, pr in zip(pts, pred)])
        res = np.hypot(*(pred - Q).T)
        new = res <= max(MAX_RESIDUAL_M, 2.5 * np.median(res[use]))
        if new.sum() < 3:
            break
        use = new
        X = similarity(P[use], Q[use])
    pred = np.c_[P, np.ones(len(P))] @ X
    res = np.hypot(*(pred - Q).T)
    snapped = 0
    if line_refs:
        _, _, lines = m.load_osm()
        refs = [lines[r] for r in line_refs if r in lines]
        L = np.array([(float(l["px"]), float(l["py"]))
                      for l in csv.DictReader((LABELS / f"{route}.csv").open(encoding="utf-8"))])
        snap = SNAP_M
        for _ in range(30):
            S = np.c_[L, np.ones(len(L))] @ X
            near = []
            for k, q in enumerate(S):
                best = None
                for ln in refs:
                    pr = min(ln.project(tuple(q)), key=lambda t: t[1])
                    if best is None or pr[1] < best[1]:
                        best = (ln.point_at(pr[0]), pr[1])
                if best and best[1] <= snap:
                    near.append((k, best[0]))
            if len(near) < 3:
                break
            Pk = np.r_[P[use], L[[k for k, _ in near]]]
            Qk = np.r_[Q[use], np.array([p for _, p in near])]
            X = similarity(Pk, Qk)
            snap = max(80, snap * 0.85)         # tighten as the fit settles
        snapped = len(near)
        pred = np.c_[P, np.ones(len(P))] @ X
        res = np.hypot(*(pred - Q).T)
    return {
        "lines": line_refs or [],
        "line_points": snapped,
        "ok": True,
        "transform": X.tolist(),
        "m_per_px": round(float(np.hypot(*X[0])), 3),
        "control": int(use.sum()),
        "dropped": [p["label"] for p, u in zip(pts, use) if not u],
        "median_m": round(float(np.median(res[use])), 1),
        "max_m": round(float(res[use].max()), 1),
    }


def main() -> int:
    routes = sys.argv[1:]
    if not routes:
        print(__doc__)
        return 1
    rows = list(csv.DictReader((ROOT / "data" / "stop_positions.csv").open(encoding="utf-8")))
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    for arg in routes:
        route, _, refs = arg.partition("=")
        out[route] = fit_route(route, rows, refs.split("+") if refs else None)
        print(route, {k: v for k, v in out[route].items() if k != "transform"})
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
