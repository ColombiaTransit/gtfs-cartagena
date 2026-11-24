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
    `line_end` are estimates that need checking; `photon` is a geocoded
    place with a matching name close to the line.
- `scripts/georef_maps.py` fits each official route map onto the OSM line and
  reads the stop markers off it (`raw/web/markers.json`). The matching uses them
  between anchors: `map_order` (counts match) or `map_aligned` (check these).
  Works for A104, A105, A107, A108, A111, X102 and partly A117/X105; schematic
  maps (T routes) do not fit. Run `python scripts/georef_maps.py [ROUTE ...]` to
  redo all maps or only the routes given.
- `data/map_labels/<route>.csv`: hand-checked link between the markers on the
  official map (pixel) and the open-data stops, made by reading the map labels.
  Used before everything but OSM stations (`map_label`); works on distorted maps
  too, by spreading stops between stations in proportion to the map distances.
  Done: A101, A102, A103, A107, A114, A117, C001, C018, T102, T103, X101,
  X103, X104, X106. A101: the map shows Carolina del Mar, El Club and Frente
  al Ara where the open data has seq 4-11 (Bomba Petromil to Cl 39H); those
  are left unlabelled. A102 and C018 maps do not fit OSM, so their stops are
  spread between anchors by map distance (C018 between shared stops).
- `data/news_stops.csv`: stop lists from the news items (`news_id` = file in
  `raw/news/text/`) for routes missing from the open data (C018, A118) or
  incomplete there (C017: the open data leaves out the 27 stops on Av.
  Santander and in the centre). They replace the open-data stops of that route
  (`source` column in `stop_positions.csv`). For these routes a stop with the
  same name as a stop of another route on the same road takes that position:
  `shared_stop` (that stop is well placed) or `shared_estimate` (it is an
  estimate itself, check it). A118 has no OSM line yet, so its stops have no
  position.
- `scripts/geocode_stops.py` (workflow *Geocode stops with Photon*) geocodes the
  estimated stops with our own Photon server into `raw/geocode/photon.json`,
  then reruns the matching. Needs the `PHOTON_URL` **secret**.
- `raw/web/`: route maps and PDF from transcaribe.gov.co/index.php/rutas-sitm/
  (workflow *Fetch Transcaribe route maps*). `data/route_hours_web.csv` holds the
  operating hours read from those maps, including the afternoon windows of
  peak-only routes that the open data leaves out, and A118/C018.
- `scripts/fetch_news.py` (workflow *Fetch Transcaribe news*, weekly and on
  demand) downloads all news items from the transcaribe.gov.co WordPress API
  into `raw/news/`: one text file per item, `index.csv` with the route codes
  and topics (paraderos, desvio, horario, frecuencia, festivo, tarifa) each
  item names, and `routes.csv` with the items per route, newest first. Use it
  for stop lists of routes missing from the open data (C017, C018, A118),
  frequency changes and special timetables (`calendar_dates.txt`).
- `data/headways_news.csv`: headways per route and time window from the news
  and El Universal, with source and start date (old figures: 2018–2024).
- `data/service_changes_news.csv`: per date range the day type used on
  holidays, suspended routes, detours with skipped stops, and extra stops or
  trips (31 Dec 2024 to Nov 2026). Basis for `calendar_dates.txt`.
  `X106-ext` is the X106 extension to the Gobernación de Bolívar.
- `docs/onderzoek.md` holds the research notes (network, timetable, fares,
  sources), in Dutch.

## Sources

- Datos Abiertos Cartagena (CC-BY):
  - *Paradero_Transcaribe 2025.xlsx* — stops per route, with departure times
  - *Rutas_Transcaribe 2025.xlsx* — routes
- transcaribe.gov.co — news on route changes and special timetables

## Next steps

1. Improve the interpolated stop positions (geocoding, OSM edits, manual checks).
2. Fix the C017 relation in OSM: it has a gap at the Crespo tunnel, and it runs
   through Crespo on the way back, while the news (5309) has it through Crespo
   (T102 stops) on the way out and through the tunnel on the way back. Until
   then most C017 stops north of Terrazas de San Sebastián are wrong.
   Add an A118 relation (Portal – Terminal – Cra 92 – Ciudadela de la Paz).
   Check X105 (stop order fits the line poorly).
3. Build `stops.txt`, `routes.txt`, `shapes.txt` and `trips.txt`/`frequencies.txt`.
4. Add fares (Fares v2).
