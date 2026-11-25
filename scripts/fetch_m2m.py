#!/usr/bin/env python3
"""
One-off snapshot of the M2M Control API behind the Mi Bus Transcaribe app
(see docs/mibus-transcaribe-api.md) into raw/m2m/. No credentials: only the
endpoints that answer without authentication.

Writes:
    raw/m2m/allLines.json                      lines with their route variants
    raw/m2m/allPoints.json                     all stops
    raw/m2m/bustop/<id_migracao>.json          stops of a variant, in order
    raw/m2m/pattern/<line id>.json             route geometry of all variants of a line
    raw/m2m/departure/<date>/<id_migracao>.json  scheduled departures on that date
    raw/m2m/manifest.json                      what was fetched, when, HTTP status,
                                               size and sha256 per file

Lines whose number starts with an EXCLUDE prefix (A000: test lines, not
official) are kept in allLines.json but their variants are not fetched.

Usage: python scripts/fetch_m2m.py DATE [DATE ...]     (YYYY-MM-DD)
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

API = "https://zn5.m2mcontrol.com.br/api/forecast/lines/load"
CLIENT = 1343
OUT = Path(__file__).resolve().parent.parent / "raw" / "m2m"
EXCLUDE = ("A000",)
PAUSE = 0.5            # seconds between requests
USER_AGENT = "ColombiaTransit-gtfs-cartagena/1.0 (+https://github.com/ColombiaTransit/gtfs-cartagena)"

SESSION = requests.Session()
SESSION.headers["User-Agent"] = USER_AGENT
manifest: dict = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": {}}


def get(path: str, params: dict | None = None) -> requests.Response | None:
    url = f"{API}/{path}/{CLIENT}"
    for attempt in range(4):
        try:
            r = SESSION.get(url, params=params, timeout=60)
            if r.status_code < 500:
                time.sleep(PAUSE)
                return r
            print(f"  {path}: HTTP {r.status_code}, retrying", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  {path}: {e}, retrying", file=sys.stderr)
        time.sleep(5 * 2 ** attempt)
    return None


def save(rel: str, r: requests.Response | None) -> object:
    entry = {"status": r.status_code if r is not None else None}
    if r is None or r.status_code != 200:
        manifest["files"][rel] = entry
        print(f"  {rel}: {entry['status']}", file=sys.stderr)
        return None
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    data = r.json()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    entry.update(bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest())
    manifest["files"][rel] = entry
    return data


def main() -> int:
    dates = sys.argv[1:]
    if not dates:
        print(__doc__)
        return 1
    for d in dates:
        date.fromisoformat(d)                     # fail early on a bad date
    OUT.mkdir(parents=True, exist_ok=True)

    lines = save("allLines.json", get("allLines"))
    save("allPoints.json", get("allPoints"))
    if not lines:
        sys.exit("allLines failed")

    variants = []
    for line in lines:
        if str(line.get("numero", "")).startswith(EXCLUDE):
            print(f"skip {line.get('numero')} {line.get('name')}")
            continue
        save(f"pattern/{line['id']}.json", get(f"pattern/{line['id']}"))   # all variants of the line
        for t in line.get("trajetos", []):
            variants.append((line.get("numero"), t["id_migracao"], t.get("nome")))
    print(f"{len(variants)} variants")

    for numero, vid, nome in variants:
        print(f"{numero} {vid} {nome}")
        save(f"bustop/{vid}.json", get(f"bustop/{vid}"))
        for d in dates:
            save(f"departure/{d}/{vid}.json", get(f"departure/{vid}", {"date": d}))

    manifest["dates"] = dates
    manifest["excluded_prefixes"] = list(EXCLUDE)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    bad = [k for k, v in manifest["files"].items() if v["status"] != 200]
    print(f"{len(manifest['files'])} files, {len(bad)} failed")
    return 1 if len(bad) > len(manifest["files"]) // 10 else 0


if __name__ == "__main__":
    sys.exit(main())
