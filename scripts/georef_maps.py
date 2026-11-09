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

# route colours by hue (degrees), so thin anti-aliased lines count too;
# teal (titles, boxes, ~185 degrees) is left out
HUES = {"green": (115, 165), "orange": (-15, 22)}
MIN_SATURATION = {"green": 0.30, "orange": 0.45}
MARKER_MIN_RADIUS = 4.5     # px; the route line is ~3 px from its centre to its edge
MARKER_MAX_RADIUS = 16     # px; anything thicker is a box, a label or a filled loop
OK_MEDIAN_M = 15            # median distance image line -> OSM line
OK_P80_M = 45               # 80% of the image line lies this close to the OSM line
OK_SHARE = 0.3              # the map shows at least this share of the OSM line


def to_m(lon, lat):
    return np.c_[np.asarray(lon) * KX, np.asarray(lat) * KY]


RGB = {"green": (45, 114, 70), "orange": (240, 83, 55)}


def colour_masks(path, mode="rgb40"):
    """Route colour masks. rgb<N>: within N of the house colours; hsv: by hue."""
    if mode.startswith("rgb"):
        im = np.array(Image.open(path).convert("RGB")).astype(int)
        tol = int(mode[3:])
        return {c: np.abs(im - np.array(rgb)).sum(2) < tol for c, rgb in RGB.items()}
    hsv = np.array(Image.open(path).convert("RGB").convert("HSV")).astype(float)
    h = hsv[..., 0] * 360 / 255
    h = np.where(h > 300, h - 360, h)
    s, v = hsv[..., 1] / 255, hsv[..., 2] / 255
    return {c: (h >= lo) & (h <= hi) & (s >= MIN_SATURATION[c]) & (v >= 0.25)
            for c, (lo, hi) in HUES.items()}


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


def icp_affine(P, S, X, iters=40, trim=0.8):
    """Affine refinement (for maps that are squeezed or stretched)."""
    T = cKDTree(S)
    A = np.c_[P, np.ones(len(P))]
    for _ in range(iters):
        Q = A @ X
        d, i = T.query(Q)
        k = d <= np.quantile(d, trim)
        X, *_ = np.linalg.lstsq(A[k], S[i[k]], rcond=None)
    Q = A @ X
    d, _ = T.query(Q)
    d2, _ = cKDTree(Q).query(S)
    return X, float(np.median(d)), float(np.quantile(d, 0.8)), float((d2 <= 40).mean())


def georef(path: Path, coords) -> dict:
    """Try a few ways of reading the colours; keep the best fit."""
    best = None
    for mode in ("rgb40", "rgb80", "hsv"):
        r = georef_mode(path, coords, mode)
        r["mask"] = mode
        key = (r.get("ok", False), -(r.get("p80_m") or 1e9))
        if best is None or key > best[0]:
            best = (key, r)
        if r.get("ok"):
            break
    return best[1]


def georef_mode(path: Path, coords, mode) -> dict:
    masks = colour_masks(path, mode)
    line = drop_small(drop_thick(masks["green"] | masks["orange"]), 80)
    # find the markers first and leave them out of the fit: on some maps they
    # are pins standing next to the line rather than discs on it
    found = {c: find_markers(m, line & m) for c, m in masks.items()}
    fit_px = line.copy()
    for P in found.values():
        for x, y in P:
            fit_px[max(0, int(y) - 20):int(y) + 21, max(0, int(x) - 20):int(x) + 21] = False
    if fit_px.sum() < 0.3 * line.sum():
        fit_px = line
    ys, xs = np.nonzero(fit_px)
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
    kind = "similarity"
    # pixel (x, y) -> metres as an affine matrix, so both kinds convert the same way
    X = np.array([[a.real, a.imag], [a.imag, -a.real], [b.real, b.imag]])
    if not (med <= OK_MEDIAN_M and p80 <= OK_P80_M):
        Xa, med_a, p80_a, share_a = icp_affine(pix, S, X)
        sv = np.linalg.svd(Xa[:2], compute_uv=False)
        # accept a moderate squeeze only; a collapsed fit is not a map
        if med_a < med and sv[1] / sv[0] > 0.5:
            X, med, p80, share, kind = Xa, med_a, p80_a, share_a, "affine"

    out = {
        "ok": med <= OK_MEDIAN_M and p80 <= OK_P80_M and share >= OK_SHARE,
        "median_m": round(med, 1),
        "p80_m": round(p80, 1),
        "share_of_line": round(share, 2),
        "fit": kind,
        "m_per_px": round(float(np.sqrt(abs(np.linalg.det(X[:2])))), 3),
        "rotation_deg": round(math.degrees(math.atan2(X[0, 1], X[0, 0])), 1),
        "transform": X.tolist(),
        "markers": [],
    }
    for colour, P in found.items():
        if not len(P):
            continue
        W = np.c_[P, np.ones(len(P))] @ X
        for (x, y), (mx, my) in zip(P, W):
            out["markers"].append({"colour": colour, "px": [int(round(x)), int(round(y))],
                                   "lat": round(my / KY, 6), "lon": round(mx / KX, 6)})
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
        if len(sys.argv) > 1 and route not in sys.argv[1:]:
            continue
        if route not in shapes:
            result[route] = {"ok": False, "reason": "no OSM line", "image": files[0]}
            print(f"{route:6s} skipped: no OSM line")
            continue
        r = georef(WEB / files[0], shapes[route])
        r["image"] = files[0]
        result[route] = r
        print(f"{route:6s} ok={r['ok']!s:5s} {r.get('mask', '')} {r.get('fit', '')} median={r.get('median_m')} p80={r.get('p80_m')} share={r.get('share_of_line')} "
              f"m/px={r.get('m_per_px')} rot={r.get('rotation_deg')} markers={len(r.get('markers', []))}")
    path = WEB / "markers.json"
    if len(sys.argv) > 1 and path.exists():
        result = {**json.loads(path.read_text()), **result}
    path.write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
