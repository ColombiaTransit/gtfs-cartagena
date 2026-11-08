# gtfs-cartagena

GTFS feed for public transport in Cartagena de Indias, Colombia — starting with
**Transcaribe**, the city's integrated mass transit system (SITM).

## Status

Research and data collection. No feed is published yet.

- `scripts/scrape_transcaribe.py` downloads the Transcaribe datasets from the
  Cartagena open-data portal (CKAN API, with the XLSX files as fallback) and
  writes the raw data to `raw/`.
- The GitHub Action *Scrape Transcaribe Open Data* runs the scraper on demand
  and uploads `raw/` as a workflow artifact.
- `raw/osm/` holds OpenStreetMap exports (stations, bus stops and the
  Transcaribe route relations), © OpenStreetMap contributors, ODbL.
- `scripts/match_stops.py` places every open-data stop on the OSM route line:
  - `data/shapes_osm.geojson`: one round-trip line per route.
  - `data/stop_positions.csv` and `.geojson`: position per route, direction
    and stop. The `method` column says how sure the position is:
    `osm_station`, `osm_named` or `osm_order` come from OSM; `osm_aligned` is
    an OSM stop paired by position; `interpolated`, `line_start` and
    `line_end` are estimates that need checking.
- `docs/onderzoek.md` holds the research notes (network, timetable, fares,
  sources), in Dutch.

## Sources

- Datos Abiertos Cartagena (CC-BY):
  - *Paradero_Transcaribe 2025.xlsx* — stops per route, with departure times
  - *Rutas_Transcaribe 2025.xlsx* — routes
- transcaribe.gov.co — news on route changes and special timetables

## Next steps

1. Improve the interpolated stop positions (geocoding, OSM edits, manual checks).
2. Fill the gaps: X103 has no OSM line yet; the C017 line is incomplete.
3. Build `stops.txt`, `routes.txt`, `shapes.txt` and `trips.txt`/`frequencies.txt`.
4. Add fares (Fares v2).
