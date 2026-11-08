#!/usr/bin/env python3
"""
Geocode the stops whose position is still an estimate, with our own Photon.

Reads   data/stop_positions.csv        (estimated stops and their rough position)
Writes  raw/geocode/photon.json        cache: per route/direction/seq the query
                                       and Photon's candidates

The Photon base URL comes from the PHOTON_URL environment variable and is
private: it is never printed, and error messages are scrubbed of it.
The server sits behind Cloudflare, so requests carry browser headers.

Only stops that are not in the cache (or whose name changed) are queried,
so reruns are cheap. scripts/match_stops.py uses the cache.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "raw" / "geocode" / "photon.json"
ESTIMATED = {"interpolated", "line_start", "line_end", "photon"}

# Cartagena urban area: min lon, min lat, max lon, max lat
BBOX = "-75.58,10.28,-75.40,10.52"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}

# words that describe where the stop is relative to a place, not the place
PREFIX = re.compile(
    r"^(frente\s+(a\s+(la|el|los|las)?|al?|de)?|al\s+frente\s+de(\s+la|\s+el)?|antes\s+de(l)?|"
    r"despu[eé]s\s+de(l)?|entrada(\s+a(l)?)?|esquina|diagonal\s+a|cerca\s+de)\s+",
    re.I,
)


def base_url() -> str:
    url = os.environ.get("PHOTON_URL", "").strip().rstrip("/")
    if not url:
        sys.exit("PHOTON_URL is not set")
    return url if url.endswith("/api") else url + "/api"


def scrub(text: str, secret: str) -> str:
    host = re.sub(r"^https?://", "", secret).split("/")[0]
    return str(text).replace(secret, "<PHOTON_URL>").replace(host, "<photon-host>")


def query_text(name: str) -> str:
    q = PREFIX.sub("", name.strip())
    q = re.sub(r"\s+", " ", q)
    return q


def main() -> int:
    api = base_url()
    session = requests.Session()
    session.headers.update(HEADERS)

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    rows = list(csv.DictReader((ROOT / "data" / "stop_positions.csv").open(encoding="utf-8")))

    todo = []
    for r in rows:
        if r["method"] not in ESTIMATED or not r["lat"]:
            continue
        key = f"{r['route']}|{r['direction']}|{r['seq']}"
        if key in cache and cache[key].get("name") == r["name"]:
            continue
        todo.append((key, r))
    print(f"{len(todo)} stops to geocode ({len(cache)} cached)")

    errors = 0
    for n, (key, r) in enumerate(todo, 1):
        q = query_text(r["name"])
        params = {"q": f"{q}, Cartagena", "lat": r["lat"], "lon": r["lon"],
                  "limit": 5, "bbox": BBOX}
        try:
            resp = session.get(api, params=params, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            feats = resp.json().get("features", [])
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"  {key}: failed ({scrub(type(exc).__name__ + ': ' + str(exc), api)})")
            if errors >= 10 and errors == n:
                print("Every request fails; stopping.")
                break
            continue
        cache[key] = {
            "name": r["name"],
            "query": q,
            "bias": [float(r["lat"]), float(r["lon"])],
            "results": [
                {
                    "lat": f["geometry"]["coordinates"][1],
                    "lon": f["geometry"]["coordinates"][0],
                    **{k: f["properties"].get(k) for k in
                       ("name", "street", "housenumber", "district", "osm_key", "osm_value",
                        "type", "osm_type", "osm_id") if f["properties"].get(k) is not None},
                }
                for f in feats
            ],
        }
        if n % 50 == 0:
            print(f"  {n}/{len(todo)}")
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        time.sleep(0.1)

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    hits = sum(1 for v in cache.values() if v["results"])
    print(f"done: {len(cache)} cached, {hits} with at least one result, {errors} errors")
    return 1 if errors and errors == len(todo) else 0


if __name__ == "__main__":
    sys.exit(main())
