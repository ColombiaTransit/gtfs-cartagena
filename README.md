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
- `docs/onderzoek.md` holds the research notes (network, timetable, fares,
  sources), in Dutch.

## Sources

- Datos Abiertos Cartagena (CC-BY):
  - *Paradero_Transcaribe 2025.xlsx* — stops per route, with departure times
  - *Rutas_Transcaribe 2025.xlsx* — routes
- transcaribe.gov.co — news on route changes and special timetables

## Next steps

1. Run the scraper and check what the datasets contain (coordinates, stop order, times).
2. Build `stops.txt`, `routes.txt` and `trips.txt`/`frequencies.txt` from them.
3. Add shapes (GraphHopper, as in the other ColombiaTransit feeds) and fares (Fares v2).
