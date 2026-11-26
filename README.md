# gtfs-cartagena

GTFS feed for public transport in Cartagena de Indias, Colombia — starting with
**Transcaribe**, the city's integrated mass transit system (SITM).

## Status

A first static feed can be built (`python scripts/build_gtfs.py` ->
`build/transcaribe-gtfs.zip`, see `docs/gtfs-design.md`): 24 routes, 638 stops,
12,584 trips, no validator errors.

**Download:** the current feed always sits at a fixed address,
<https://github.com/ColombiaTransit/gtfs-cartagena/releases/latest/download/transcaribe-gtfs.zip>
(release `latest`). Each version is also kept as a dated release
(`v2026-11-26`, ...), with the validation report attached.

- `scripts/scrape_transcaribe.py` downloads the Transcaribe datasets from the
  Cartagena open-data portal (CKAN API, with the XLSX files as fallback) and
  writes the raw data to `raw/`.
- The GitHub Action *Scrape Transcaribe Open Data* runs the scraper on demand
  and uploads `raw/` as a workflow artifact.
- `raw/osm/` holds OpenStreetMap exports (stations, bus stops, the
  Transcaribe route relations, the road network and named places),
  © OpenStreetMap contributors, ODbL. `scripts/fetch_osm.py` (workflow *Fetch
  OSM data from Overpass*) refreshes them from our own Overpass server and
  reruns the matching. Needs the `OVERPASS_URL` **secret**.
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
  Done: A101, A102, A103, A104, A105, A107, A111, A114, A117, A118, C001,
  C017, C018, T102, T103, X101, X102, X103, X104, X105, X106. A101: the map shows Carolina del Mar, El Club and Frente
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
  estimate itself, check it).
- `scripts/fit_map_labels.py` georeferences a map from its labelled stops, for
  routes whose OSM line is missing or wrong: control points are labelled stops
  with the name of a well-placed stop of another route, refined with OSM lines
  the map follows (`ROUTE=LINE+LINE`). Writes `data/map_labels/transforms.json`;
  `match_stops.py` then places every labelled stop of that route at its map
  position, pulled onto one of those lines when within 120 m (`map_georef`).
  OSM stations stay at the station, other stops go straight between their
  neighbours. Used for C017 (`C017=C017`), A118 (`A118=C016+A101+A117+A114+X104`;
  the Carrera 92 stops are unsnapped map positions), X105 (`X105=X105`) and,
  with the `georef_maps.py` fit (`"from": "markers"`), A105 (OSM runs the
  Simón Bolívar loop the other way round).
- Last pass of `match_stops.py`: a stop that is still an estimate takes the
  place of a well-placed stop of another route with the same name on its own
  line (`shared_stop`, e.g. the T102 stops in Crespo from C017), or of a named
  place from `raw/osm/pois.csv` with the same name near its line (`osm_poi`).
  Numbers count in the name match ("Calle 67" is not "Calle 70").
- `scripts/build_stops.py` (#24) turns the positions per route into GTFS
  stops: `data/stops.csv` (stops.txt columns plus `quality` and `routes`) and
  `data/stop_ids.csv` (route, direction, seq -> stop_id). Trunk stations become
  `location_type=1` with one platform per vagón code (A1, B2, ...; at Patio
  Portal the bays), placed on the vagón's part of the OSM platform from
  `raw/osm/overpass_stations.json` (vagón A assumed nearest Patio Portal: to
  check). Street stops of several routes are merged when they have the same
  name, lie within 300 m and the buses go the same way, or lie on the same
  spot; the position comes from the best-placed route. `data/stops_review.csv`
  lists the merges to check (different names, or routes placing them far apart).
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
- `docs/mibus-transcaribe-api.md`: the API behind the *Mi Bus Transcaribe*
  app (M2M Control): lines, stops per route variant in order, scheduled
  departures and route geometry, without authentication. Decided to use it
  for a one-off static feed (no daily refresh, no realtime for now); licensing
  settled 2026-11-26.
- `docs/onderzoek.md` holds the research notes (network, timetable, fares,
  sources), in Dutch.

## Sources

- Datos Abiertos Cartagena (CC-BY):
  - *Paradero_Transcaribe 2025.xlsx* — stops per route, with departure times
  - *Rutas_Transcaribe 2025.xlsx* — routes
- transcaribe.gov.co — news on route changes and special timetables

## Next steps

1. Check the remaining estimated stops (C016, T102, X101, A101) and the
   `map_georef` stops on a map; positions from map labels are typically within
   50 m, but where several routes label the same stop they can differ by more.
2. Shapes: generate them from the stops (routing) rather than taking the OSM
   relations; the C017 relation runs the Crespo loop the wrong way round and
   has a gap at the tunnel, A118 has none, X105 leaves the trunk outbound.
3. Build `stops.txt`, `routes.txt`, `shapes.txt` and `trips.txt`/`frequencies.txt`.
4. Add fares (Fares v2).
