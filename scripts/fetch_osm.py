#!/usr/bin/env python3
"""
Export the OpenStreetMap data the feed needs from our own Overpass server
into raw/osm/. Data © OpenStreetMap contributors, ODbL.

The Overpass URL comes from the OVERPASS_URL environment variable (the
interpreter endpoint, e.g. https://example.org/api/interpreter). It is kept
out of the log and of error messages.

Writes:
- overpass_stops.json   bus stops, platforms, stop positions, stations
                        (same query and format as before; match_stops.py)
- overpass_routes.json  Transcaribe route relations with all members, their
                        nodes and their ways with geometry (same format;
                        operator ~ "caribe" also catches the "Trasncaribe" typo)
- roads.geojson.gz      the drivable road network: one LineString per way with
                        its OSM node ids, for routing shapes and snapping stops
- pois.csv              named places (schools, churches, shops, parks, ...)
                        that stops are named after, with their centre

Usage: OVERPASS_URL=... python scripts/fetch_osm.py [stops] [routes] [roads] [pois]
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

OUT = Path(__file__).resolve().parent.parent / "raw" / "osm"
BBOX = "10.28,-75.58,10.52,-75.40"          # south, west, north, east (Cartagena + Turbaco road)

QUERIES = {
    "stops": f"""[out:json][timeout:300];
(
  node["highway"="bus_stop"]({BBOX});
  nwr["public_transport"~"^(platform|stop_position|station)$"]({BBOX});
  nwr["amenity"="bus_station"]({BBOX});
  relation["type"="route"]["route"~"^(bus|trolleybus)$"]({BBOX});
  relation["type"="route_master"]["route_master"~"^(bus|trolleybus)$"]({BBOX});
);
out center tags;""",
    "routes": f"""[out:json][timeout:300];
relation["type"="route"]["route"="bus"]["operator"~"caribe",i]({BBOX})->.r;
.r out body;
node(r.r);
out;
way(r.r);
out geom;""",
    "roads": f"""[out:json][timeout:600];
way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|busway|road)(_link)?$"]({BBOX});
out geom;""",
    "pois": f"""[out:json][timeout:600];
(
  nwr["name"]["amenity"]({BBOX});
  nwr["name"]["shop"]({BBOX});
  nwr["name"]["leisure"]({BBOX});
  nwr["name"]["tourism"]({BBOX});
  nwr["name"]["office"]({BBOX});
  nwr["name"]["healthcare"]({BBOX});
  nwr["name"]["craft"]({BBOX});
  nwr["name"]["historic"]({BBOX});
  nwr["name"]["building"]({BBOX});
  nwr["name"]["place"~"^(neighbourhood|suburb|quarter|square|locality)$"]({BBOX});
);
out center tags;""",
}

ROAD_TAGS = ("highway", "name", "ref", "oneway", "junction", "access", "bus", "psv", "lanes", "maxspeed")
POI_KEYS = ("amenity", "shop", "leisure", "tourism", "office", "healthcare", "craft", "historic", "place", "building")


def server() -> tuple[str, callable]:
    url = os.environ.get("OVERPASS_URL", "").strip()
    if not url:
        sys.exit("OVERPASS_URL is not set")
    host = urlparse(url).netloc or url
    return url, lambda text: str(text).replace(url, "<OVERPASS_URL>").replace(host, "<overpass-host>")


def query(url: str, scrub, name: str, q: str) -> dict:
    for attempt in range(4):
        try:
            r = requests.post(url, data={"data": q}, timeout=900,
                              headers={"User-Agent": "ColombiaTransit-gtfs-cartagena/1.0"})
            if r.status_code == 200:
                data = r.json()
                if data.get("remark", "").lower().startswith(("runtime error", "error")):
                    raise RuntimeError(data["remark"][:300])
                return data
            print(f"{name}: HTTP {r.status_code} {scrub(r.text[:200])}", file=sys.stderr)
        except Exception as e:                                    # noqa: BLE001
            print(f"{name}: {scrub(e)}", file=sys.stderr)
        time.sleep(30 * (attempt + 1))
    sys.exit(f"{name}: Overpass query failed")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def write_roads(data: dict) -> int:
    feats = []
    for e in data["elements"]:
        if e["type"] != "way" or "geometry" not in e:
            continue
        t = e.get("tags", {})
        feats.append({"type": "Feature", "id": e["id"],
                      "properties": {"nodes": e["nodes"], **{k: t[k] for k in ROAD_TAGS if k in t}},
                      "geometry": {"type": "LineString",
                                   "coordinates": [[round(g["lon"], 7), round(g["lat"], 7)] for g in e["geometry"]]}})
    feats.sort(key=lambda f: f["id"])
    body = json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":"))
    # mtime=0: the file only changes when the data does
    with gzip.GzipFile(OUT / "roads.geojson.gz", "wb", mtime=0) as fh:
        fh.write(body.encode("utf-8"))
    return len(feats)


def write_pois(data: dict) -> int:
    rows = []
    for e in data["elements"]:
        t = e.get("tags", {})
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        if lat is None or not t.get("name"):
            continue
        kind = next((f"{k}={t[k]}" for k in POI_KEYS if k in t), "")
        rows.append({"osm_id": f"{e['type'][0]}{e['id']}", "lat": round(lat, 7), "lon": round(lon, 7),
                     "name": t["name"], "kind": kind, "addr": " ".join(
                         t[k] for k in ("addr:street", "addr:housenumber") if k in t)})
    rows.sort(key=lambda r: r["osm_id"])
    with (OUT / "pois.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["osm_id", "lat", "lon", "name", "kind", "addr"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main() -> int:
    parts = sys.argv[1:] or list(QUERIES)
    unknown = set(parts) - set(QUERIES)
    if unknown:
        sys.exit(f"unknown part(s): {', '.join(sorted(unknown))}")
    url, scrub = server()
    OUT.mkdir(parents=True, exist_ok=True)
    for name in parts:
        data = query(url, scrub, name, QUERIES[name])
        n = len(data.get("elements", []))
        if name in ("stops", "routes"):
            if name == "routes" and not any(e["type"] == "relation" for e in data["elements"]):
                sys.exit("routes: no relations returned, keeping the old file")
            data.pop("osm3s", None)                  # timestamps would change the file on every run
            write_json(OUT / f"overpass_{name}.json", data)
        elif name == "roads":
            n = write_roads(data)
        else:
            n = write_pois(data)
        print(f"{name}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
