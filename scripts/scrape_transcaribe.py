#!/usr/bin/env python3

"""
Scrape Cartagena Open Data / Transcaribe.

Primary source:
    CKAN Datastore API

Fallback:
    Official XLSX download

Outputs:
    raw/transcaribe_stops.json
    raw/transcaribe_stops.csv
    raw/transcaribe_routes.json
    raw/transcaribe_routes.csv
    raw/transcaribe_metadata.json
    raw/transcaribe_debug.json

The scraper deliberately keeps raw data so that changes in the
Cartagena open-data portal can be inspected later.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import sys
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import pandas as pd
import requests


BASE_URL = "https://datosabiertos.cartagena.gov.co"

# Transcaribe "Paradero_Transcaribe 2025.xlsx"
STOPS_RESOURCE_ID = "886f50a8-88f0-4e07-9b71-f5bbe4ae7daf"

# Transcaribe "Rutas_Transcaribe 2025.xlsx"
ROUTES_RESOURCE_ID = "ab94769a-5f6b-41ad-a5ca-3a4ed8812edf"

PACKAGE_ID = "67d77dfa-57b9-40e3-90f3-c9a44a804595"

STOPS_DOWNLOAD_URL = (
    f"{BASE_URL}/dataset/{PACKAGE_ID}/resource/"
    f"{STOPS_RESOURCE_ID}/download/paradero_transcaribe-2025.xlsx"
)

ROUTES_DOWNLOAD_URL = (
    f"{BASE_URL}/dataset/rutas-del-sistema-integrado-de-transporte-masivo-"
    f"transcaribe-s-a-cartagena/resource/{ROUTES_RESOURCE_ID}/download/"
    f"rutas_transcaribe-2025.xlsx"
)

API_BASE = f"{BASE_URL}/api/3/action"

OUT_DIR = Path(os.environ.get("OUTPUT_DIR", "raw"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("transcaribe")


SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "ColombiaTransit/TranscaribeScraper "
            "(GitHub Actions; open-data research)"
        ),
        "Accept": "*/*",
    }
)


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    # Preserve the order in which fields first occur.
    fields = []
    seen = set()

    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)

    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (dict, list))
                        else value
                    )
                    for key, value in row.items()
                }
            )


def request_json(url: str, params: dict[str, Any] | None = None) -> Any:
    log.info("GET %s", url)

    response = SESSION.get(
        url,
        params=params,
        timeout=60,
    )

    log.info(
        "HTTP %s (%s bytes)",
        response.status_code,
        len(response.content),
    )

    response.raise_for_status()

    return response.json()


def datastore_search(
    resource_id: str,
    limit: int = 1000,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Retrieve a complete CKAN datastore.

    Uses pagination so this also works if the resource contains
    more than 1000 records.
    """

    url = f"{API_BASE}/datastore_search"

    rows: list[dict[str, Any]] = []
    offset = 0
    metadata = {}

    while True:
        params = {
            "resource_id": resource_id,
            "limit": limit,
            "offset": offset,
        }

        data = request_json(url, params)

        if not data.get("success"):
            raise RuntimeError(
                f"CKAN datastore_search failed: {data}"
            )

        result = data["result"]

        if not metadata:
            metadata = {
                "resource_id": result.get("resource_id"),
                "fields": result.get("fields", []),
                "total": result.get("total"),
            }

        batch = result.get("records", [])

        if not batch:
            break

        rows.extend(batch)

        log.info(
            "Retrieved %d records (total so far: %d)",
            len(batch),
            len(rows),
        )

        if len(batch) < limit:
            break

        offset += len(batch)

        # Be polite to the public API.
        time.sleep(0.5)

    return rows, metadata


def download_xlsx(url: str, output_name: str) -> pd.DataFrame:
    """
    Download the official XLSX as a fallback.
    """

    log.info("Attempting XLSX fallback: %s", url)

    response = SESSION.get(
        url,
        timeout=120,
        allow_redirects=True,
    )

    log.info(
        "XLSX HTTP %s (%s bytes)",
        response.status_code,
        len(response.content),
    )

    response.raise_for_status()

    content_type = response.headers.get("content-type", "")

    # Save the actual response for debugging.
    raw_path = OUT_DIR / output_name
    raw_path.write_bytes(response.content)

    log.info("Saved XLSX to %s", raw_path)

    if "text/html" in content_type.lower():
        raise RuntimeError(
            "Download returned HTML instead of XLSX. "
            "Likely Cloudflare or an error page."
        )

    return pd.read_excel(io.BytesIO(response.content))


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    df = df.where(pd.notnull(df), None)

    return [
        {
            str(key): value
            for key, value in row.items()
        }
        for row in df.to_dict(orient="records")
    ]


def build_route_summary(
    stop_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Reconstruct route-level information from the stop datastore.

    A route appears on multiple stops, so keep one representative
    record per route + direction.
    """

    route_fields = [
        "Codigo_Rutas",
        "Rutas",
        "Tipo",
        "Descripcion",
        "Sentido",
        "Horario_Lunes-Viernes_Salida1",
        "Horario_Lunes-Viernes_Salida2",
        "Horario_Sabado_Salida1",
        "Horario_Sabado_Salida2",
        "Horario_Domingo-Festivo_Salida1",
        "Horario_Domingo-Festivo_Salida2",
        "Nota",
        "Fecha_Activacion",
    ]

    groups: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()

    for row in stop_rows:
        route_code = str(
            row.get("Codigo_Rutas") or ""
        ).strip()

        direction = str(
            row.get("Sentido") or ""
        ).strip()

        if not route_code:
            continue

        key = (route_code, direction)

        if key not in groups:
            groups[key] = {
                field: row.get(field)
                for field in route_fields
                if field in row
            }

    return list(groups.values())


def main() -> int:

    debug: dict[str, Any] = {
        "base_url": BASE_URL,
        "stops_resource_id": STOPS_RESOURCE_ID,
        "routes_resource_id": ROUTES_RESOURCE_ID,
        "methods": {},
    }

    # ------------------------------------------------------------
    # STOPS
    # ------------------------------------------------------------

    stops: list[dict[str, Any]] = []
    stops_metadata: dict[str, Any] = {}

    try:
        stops, stops_metadata = datastore_search(
            STOPS_RESOURCE_ID
        )

        debug["methods"]["stops_datastore"] = {
            "success": True,
            "records": len(stops),
            "metadata": stops_metadata,
        }

        log.info(
            "Successfully retrieved %d stop records via CKAN.",
            len(stops),
        )

    except Exception as exc:
        log.warning(
            "Stops datastore failed: %s",
            exc,
        )

        debug["methods"]["stops_datastore"] = {
            "success": False,
            "error": repr(exc),
        }

        # XLSX fallback
        try:
            df = download_xlsx(
                STOPS_DOWNLOAD_URL,
                "paradero_transcaribe-2025.xlsx",
            )

            stops = dataframe_to_records(df)

            debug["methods"]["stops_xlsx"] = {
                "success": True,
                "records": len(stops),
            }

            log.info(
                "Successfully retrieved %d stop records via XLSX.",
                len(stops),
            )

        except Exception as fallback_exc:
            debug["methods"]["stops_xlsx"] = {
                "success": False,
                "error": repr(fallback_exc),
            }

            log.error(
                "Both stop retrieval methods failed."
            )

    # Save stops.
    if stops:
        write_json(
            OUT_DIR / "transcaribe_stops.json",
            stops,
        )

        write_csv(
            OUT_DIR / "transcaribe_stops.csv",
            stops,
        )

        route_summary = build_route_summary(stops)

        write_json(
            OUT_DIR / "transcaribe_routes_from_stops.json",
            route_summary,
        )

        write_csv(
            OUT_DIR / "transcaribe_routes_from_stops.csv",
            route_summary,
        )

        debug["route_summary"] = {
            "routes": len(route_summary),
        }

    # ------------------------------------------------------------
    # ROUTES
    # ------------------------------------------------------------

    routes: list[dict[str, Any]] = []
    routes_metadata: dict[str, Any] = {}

    try:
        routes, routes_metadata = datastore_search(
            ROUTES_RESOURCE_ID
        )

        debug["methods"]["routes_datastore"] = {
            "success": True,
            "records": len(routes),
            "metadata": routes_metadata,
        }

        log.info(
            "Successfully retrieved %d route records via CKAN.",
            len(routes),
        )

    except Exception as exc:
        log.warning(
            "Routes datastore failed: %s",
            exc,
        )

        debug["methods"]["routes_datastore"] = {
            "success": False,
            "error": repr(exc),
        }

        try:
            df = download_xlsx(
                ROUTES_DOWNLOAD_URL,
                "rutas_transcaribe-2025.xlsx",
            )

            routes = dataframe_to_records(df)

            debug["methods"]["routes_xlsx"] = {
                "success": True,
                "records": len(routes),
            }

            log.info(
                "Successfully retrieved %d route records via XLSX.",
                len(routes),
            )

        except Exception as fallback_exc:
            debug["methods"]["routes_xlsx"] = {
                "success": False,
                "error": repr(fallback_exc),
            }

            log.error(
                "Both route retrieval methods failed."
            )

    if routes:
        write_json(
            OUT_DIR / "transcaribe_routes.json",
            routes,
        )

        write_csv(
            OUT_DIR / "transcaribe_routes.csv",
            routes,
        )

    # ------------------------------------------------------------
    # Metadata/debug
    # ------------------------------------------------------------

    debug["summary"] = {
        "stop_records": len(stops),
        "route_records": len(routes),
    }

    write_json(
        OUT_DIR / "transcaribe_metadata.json",
        {
            "stops": stops_metadata,
            "routes": routes_metadata,
        },
    )

    write_json(
        OUT_DIR / "transcaribe_debug.json",
        debug,
    )

    # We consider the scraper successful if at least one source
    # produced data.
    if not stops and not routes:
        log.error("No Transcaribe data was retrieved.")
        return 1

    log.info("Scrape completed successfully.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

