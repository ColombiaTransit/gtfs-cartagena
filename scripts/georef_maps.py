#!/usr/bin/env python3
"""
Georeference the Transcaribe route maps (raw/web/*.png) and read the stop
markers off them.

The maps are drawn on a real street map, rotated and scaled. For each route:
  1. take the pixels of the route line (green and orange),
  2. fit a similarity transform (scale, rotation, shift) onto the OSM route
     line from data/shapes_osm.geojson with iterative closest point; many
     maps show only part of the route, so the fit is judged on how well the
     image line lies on the OSM line, plus a minimum share of the route,
  3. find the stop markers (filled discs, thicker than the line) per colour
     and convert them to lat/lon.

Writes raw/web/markers.json: per route the fit quality, the transform and the
markers. Maps that do not fit (schematic diagrams such as T100E/T101) are
kept with "ok": false so scripts/match_stops.py ignores them.
"""

from __future__ import annotations

import json
import math
import warnings
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

warnings.filterwarnings("ignore", module="PIL")

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "raw" / "web"

LAT0 = 10.4
KX = 111320 * math.cos(math.radians(LAT0))
KY = 110574

COLOURS = {"green": (45, 114, 70), "orange": (240, 83, 55)}
COLOUR_TOL = 40
MARKER_MIN_RADIUS = 4.5     # px; the route line is ~3 px from its centre to its edge
MARKER_MAX_RADIUS = 12     # px; anything thicker is a box, a label or a filled loop
OK_MEDIAN_M = 15            # median distance image line -> OSM line
OK_P80_M = 45               # 80% of the image line lies this close to the OSM line
OK_SHARE = 0.3              # the map shows at least this share of the OSM line


def to_m(lon, lat):
    return np.c_[np.asarray(lon) * KX, np.asarray(lat) * KY]


def colour_mask(im, rgb):
    return np.abs(im - np.array(rgb)).sum(2) < COLOUR_TOL


def drop_small(mask, minsize=200):
    lab, n = ndi.label(mask)
    if n == 0:
        return mask
    sizes = ndi.sum(mask, lab, range(1, n + 1))
    return np.isin(lab, 1 + np.flatnonzero(sizes >= minsize))


def drop_thick(mask):
    """Remove boxes, pills and big text: components thicker than a marker."""
    lab, n = ndi.label(mask)
    if n == 0:
        return mask
    d = ndi.distance_transform_edt(mask)
    thick = ndi.maximum(d, lab, range(1, n + 1))
    return np.isin(lab, 1 + np.flatnonzero(np.asarray(thick) <= MARKER_MAX_RADIUS))


def find_markers(mask, line):
    """Discs (or rings) clearly thicker than the route line, lying on it."""
    # some maps draw rings (bus icon in a circle) instead of discs: fill them,
    # but leave large closed loops of the route line alone
    filled = mask.copy()
    holes = ndi.binary_fill_holes(mask) & ~mask
    lab, n = ndi.label(holes)
    if n:
        sizes = ndi.sum(holes, lab, range(1, n + 1))
        filled |= np.isin(lab, 1 + np.flatnonzero(sizes <= math.pi * MARKER_MAX_RADIUS ** 2))
    d = ndi.distance_transform_edt(filled)
    half_width = np.percentile(ndi.distance_transform_edt(line)[line], 90) if line.any() else 3
    lo = max(MARKER_MIN_RADIUS, 1.5 * half_width)
    near_line = ndi.binary_dilation(line, iterations=25)
    peaks = (d == ndi.maximum_filter(d, size=9)) & (d >= lo) & (d <= max(MARKER_MAX_RADIUS, 3 * half_width)) & near_line
    lab, n = ndi.label(peaks)
    if n == 0:
        return np.zeros((0, 2))
    return np.array([(x, y) for y, x in ndi.center_of_mass(peaks, lab, range(1, n + 1))])


def densify(P, step=10.0):
    out = [P[0]]
    for a, b in zip(P, P[1:]):
        n = max(1, int(np.linalg.norm(b - a) / step))
        out.extend(a + (b - a) * k / n for k in range(1, n + 1))
    return np.array(out)


# image pixel (x, y down) as complex number with y up; transform w = a*z + b
def cz(P):
    return P[:, 0] - 1j * P[:, 1]


def fit(z, w):
    zm, wm = z.mean(), w.mean()
    a = ((w - wm) * np.conj(z - zm)).sum() / (abs(z - zm) ** 2).sum()
    return a, wm - a * zm


def icp(z, Sw, a, b, iters, trim=0.85, symmetric=True):
    """
    Symmetric ICP pulls the whole OSM line onto the image (maps showing the
    whole route); one-sided ICP only pulls the image onto the OSM line (maps
    showing part of it).
    """
    S2 = np.c_[Sw.real, Sw.imag]
    T = cKDTree(S2)
    for _ in range(iters):
        q = a * z + b
        Q2 = np.c_[q.real, q.imag]
        d, i = T.query(Q2)
        k = d <= np.quantile(d, trim)
        src, dst = z[k], Sw[i[k]]
        if symmetric:
            d2, i2 = cKDTree(Q2).query(S2)
            k2 = d2 <= np.quantile(d2, trim)
            src, dst = np.r_[src, z[i2[k2]]], np.r_[dst, Sw[k2]]
        a, b = fit(src, dst)
    q = a * z + b
    Q2 = np.c_[q.real, q.imag]
    d, _ = T.query(Q2)
    d2, _ = cKDTree(Q2).query(S2)
    return a, b, float(np.median(d)), float(np.quantile(d, 0.8)), float((d2 <= 40).mean())


def georef(path: Path, coords) -> dict:
    im = np.array(Image.open(path).convert("RGB")).astype(int)
    masks = {c: colour_mask(im, rgb) for c, rgb in COLOURS.items()}
    line = drop_small(drop_thick(masks["green"] | masks["orange"]))
    ys, xs = np.nonzero(line)
    if len(xs) < 500:
        return {"ok": False, "reason": "no route line found"}
    pix = np.c_[xs, ys].astype(float)
    pix = pix[np.random.default_rng(0).choice(len(pix), min(5000, len(pix)), replace=False)]
    z = cz(pix)
    S = densify(to_m(*np.array(coords).T))
    Sw = S[:, 0] + 1j * S[:, 1]
    s0 = math.sqrt((abs(Sw - Sw.mean()) ** 2).mean() / (abs(z - z.mean()) ** 2).mean())

    def score(r):
        return r[3] if r[4] >= OK_SHARE else float("inf")

    best = None
    for symmetric in (True, False):
        for scale in ((1.0,) if symmetric else (1.0, 0.6, 0.35)):
            for deg in range(0, 360, 15):
                a0 = s0 * scale * complex(math.cos(math.radians(deg)), math.sin(math.radians(deg)))
                r = icp(z, Sw, a0, Sw.mean() - a0 * z.mean(), 20, symmetric=symmetric)
                r = icp(z, Sw, r[0], r[1], 15, trim=0.8, symmetric=False)
                if best is None or score(r) < score(best):
                    best = r
    a, b, med, p80, share = icp(z, Sw, best[0], best[1], 40, trim=0.8, symmetric=False)

    out = {
        "ok": med <= OK_MEDIAN_M and p80 <= OK_P80_M and share >= OK_SHARE,
        "median_m": round(med, 1),
        "p80_m": round(p80, 1),
        "share_of_line": round(share, 2),
        "m_per_px": round(abs(a), 3),
        "rotation_deg": round(math.degrees(np.angle(a)), 1),
        "transform": [a.real, a.imag, b.real, b.imag],
        "markers": [],
    }
    for colour, mask in masks.items():
        P = find_markers(mask, line & mask)
        if not len(P):
            continue
        w = a * cz(P) + b
        for (x, y), m in zip(P, w):
            out["markers"].append({"colour": colour, "px": [int(round(x)), int(round(y))],
                                   "lat": round(m.imag / KY, 6), "lon": round(m.real / KX, 6)})
    return out


def main() -> int:
    index = json.loads((WEB / "index.json").read_text())
    shapes = {f["properties"]["route"]: f["geometry"]["coordinates"]
              for f in json.loads((ROOT / "data" / "shapes_osm.geojson").read_text())["features"]}
    result = {}
    for key, files in sorted(index.items()):
        if not key.startswith("Ruta "):
            continue
        route = key[5:]
        if route not in shapes:
            result[route] = {"ok": False, "reason": "no OSM line", "image": files[0]}
            print(f"{route:6s} skipped: no OSM line")
            continue
        r = georef(WEB / files[0], shapes[route])
        r["image"] = files[0]
        result[route] = r
        print(f"{route:6s} ok={r['ok']!s:5s} median={r.get('median_m')} p80={r.get('p80_m')} share={r.get('share_of_line')} "
              f"m/px={r.get('m_per_px')} rot={r.get('rotation_deg')} markers={len(r.get('markers', []))}")
    (WEB / "markers.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
