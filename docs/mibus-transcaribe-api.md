# API Research – Mi Bus Transcaribe

**Project:** ColombiaTransit – GTFS Cartagena  
**Research date:** 2026-11-25  
**Source:** Mi Bus Transcaribe Android application, version 1.2  
**Status:** Endpoints validated; decided to use the API for a one-off static feed (see section 0)

## 0. Decisions (2026-11-25)

- **Use:** the M2M Control API is the source for a **one-off static GTFS feed**
  (routes, stops per route variant, scheduled departures and shapes). The existing sources (open data, news, OSM,
  route maps) are used to check it and to fill gaps.
- **No daily refresh.** The data is collected once (per service day type, see
  10.4) and kept in the repo as a snapshot; no scheduled workflow.
- **No GTFS Realtime for now.** Sections 11.2-11.3 and 18 stay as notes for later.
- **No credentials.** Only endpoints that answer without authentication are used.
  The web service credentials in the APK are not used or stored.
- **Licensing settled** (2026-11-26); the feed is published as a GitHub release.
- The repository structure in section 19 is not adopted; the collector and raw
  data follow the existing layout (`scripts/`, `raw/m2m/`).

## 1. Introduction

The Android application Mi Bus Transcaribe was statically analyzed to identify API endpoints and data sources that could be used to generate a GTFS dataset for the Transcaribe public transport system in Cartagena, Colombia.

The application uses the MeuOnibus platform developed by M2M Control. The platform provides public transport information, including routes, stops, route geometries, departure schedules and real-time arrival predictions.

Initial API requests confirmed that route and stop data can be retrieved without authentication.

## 2. Application information

| Property | Value |
|---|---|
| Application | Mi Bus Transcaribe |
| Version | 1.2 |
| Version code | 5 |
| Android package | `br.com.m2m.meuonibus.transcaribe` |
| APK source | APKPure |
| Platform | MeuOnibus |
| Technology provider | M2M Control |
| Customer ID | `1343` |
| Country | Colombia |
| Service area | Cartagena and surrounding areas |

The application contains native Android DEX files and configuration files. No complete offline public transport dataset was identified during the initial analysis.

## 3. API configuration

The primary API configuration was identified in:

`assets/config.properties`

### 3.1 Primary API

Base URL:

`https://zn5.m2mcontrol.com.br/api`

Customer ID:

`1343`

The tested endpoints return JSON responses over HTTPS.

### 3.2 Legacy API

An older, commented-out API URL was identified:

`http://previsao.m2mfrota.com.br/api`

This endpoint has not been tested and should not be used as the primary data source.

### 3.3 Authentication

The application contains web service credentials, but the following endpoints have been successfully accessed without providing credentials, authentication headers or session cookies:

- `allLines`
- `allPoints`

Authentication requirements for the remaining endpoints have not yet been established.

## 4. API endpoint inventory

All paths listed below were identified in the application configuration. Only endpoints marked as validated have been tested successfully.

| Method | Endpoint | Purpose | Status |
|---|---|---|---|
| GET | `/forecast/lines/load/allLines/1343` | All bus lines and route variants | Validated |
| GET | `/forecast/lines/load/allPoints/1343` | All bus stops | Validated |
| GET | `/forecast/lines/load/pattern/{lineId}/1343` | Route geometry of all variants of a line | Validated |
| GET | `/forecast/lines/load/bustop/{id_migracao}/1343` | Stops associated with a route variant | Validated |
| GET | `/forecast/lines/load/departure/{id_migracao}/1343` | Scheduled departures | Validated |
| GET* | `/forecast/lines/load/linesFromBusstop/{stopId}/1343` | Lines serving a stop | Untested |
| GET | `/forecast/lines/load/forecast/lines/fromPoint/{stopId}/1343` | Arrival predictions at a stop, all lines | Validated (see 11.5) |
| GET | `/forecast/lines/load/all/forecast/{stopId}/{id_migracao}/1343` | Arrival predictions at a stop for one variant | Validated (see 11.5) |
| GET* | `/forecast/lines/load/busStop/{lat}/{lon}/1343?radiusInMeters={radius}` | Nearby stops | Untested |
| Unknown | `/forecast/contact/1343` | Contact service | Untested |

\* HTTP method and parameter semantics remain to be validated.

**Identifiers:** `bustop` and `departure` take the numeric
`trajetos[].id_migracao` of a route variant (e.g. `20337`); `pattern` takes the
numeric line id `allLines[].id` (e.g. `9892` for A102) and returns all variants
of that line. With the MongoDB ids they return a client error, and `pattern`
with an `id_migracao` returns something that is not JSON (tested 2026-11-25).

## 5. Bus lines

### 5.1 Endpoint

`GET https://zn5.m2mcontrol.com.br/api/forecast/lines/load/allLines/1343`

### 5.2 Example request

```powershell
curl.exe -i "https://zn5.m2mcontrol.com.br/api/forecast/lines/load/allLines/1343"
```

### 5.3 Validated response

| Property | Value |
|---|---|
| HTTP status | 200 OK |
| Content type | application/json; charset=utf-8 |
| Content length | 23,502 bytes |
| Authentication | Not required for tested request |
| Test date | 2026-11-25 |

### 5.4 Example response

```json
{
  "id": 9892,
  "idLinha": "659b60837b35aa4792d76aa0",
  "name": "A102 U. TECNOLÓGICA - PORTAL",
  "shortName": "A102 U. TECNOLÓGICA - PORTAL",
  "numero": "A102",
  "trajetos": [
    {
      "_id": "659b60837b35aa4792d76a9f",
      "id": "659b60837b35aa4792d76a9f",
      "id_migracao": 20337,
      "kmTrajeto": 3.9,
      "nome": "A102_IDA - PORTAL - U. TECNOLOGICA",
      "startPoint": {
        "_id": "658dda9ea5ba2d1568a6bafb",
        "id_migracao": 242523
      },
      "endPoint": {
        "_id": "658dda9ea5ba2d1568a6ba45",
        "id_migracao": 242203
      }
    }
  ]
}
```

The example has been shortened for documentation purposes.

### 5.5 Data model

| Field | Description |
|---|---|
| `id` | Numeric line identifier |
| `idLinha` | MongoDB line identifier |
| `name` | Full line name |
| `shortName` | Display name |
| `numero` | Public route number |
| `trajetos` | Associated route variants |
| `empresas` | Associated transport operators |
| `trajetos[].id` | Route variant identifier |
| `trajetos[].id_migracao` | Legacy route variant identifier |
| `trajetos[].kmTrajeto` | Route variant length in kilometres |
| `trajetos[].nome` | Route variant name |
| `trajetos[].startPoint` | Starting stop |
| `trajetos[].endPoint` | Final stop |

### 5.6 Route inventory

The preliminary inventory contains 26 line records and 50 route variants.

| Route | Variants |
|---|---:|
| A000 – Test route | 2 |
| A000 – Portal–Terminal | 2 |
| A101 | 1 |
| A102 | 2 |
| A103 | 2 |
| A104 | 2 |
| A105 | 2 |
| A107 | 2 |
| A108 | 2 |
| A111 | 1 |
| A114 | 2 |
| A117 | 2 |
| A118 | 2 |
| C001 | 2 |
| C017 | 1 |
| C018 | 2 |
| T100E | 2 |
| T101 | 2 |
| T102 | 2 |
| T103 | 2 |
| X101 | 2 |
| X102 | 2 |
| X103 | 2 |
| X104 | 2 |
| X105 | 2 |
| X106 | 3 |
| **Total** | **50** |

### 5.7 Route categories

The following route prefixes are present in the dataset.

| Prefix | Interpretation |
|---|---|
| A | Alimentadora – feeder services |
| T | Troncal – trunk services |
| X | Complementary services |
| C | Complementary or other services |

The exact official classification of the X and C route categories should be verified against Transcaribe documentation.

### 5.8 Special routes

| Route | Observation | Recommendation |
|---|---|---|
| A000 – Prueba Programación | Appears to be a test route | Exclude from publication unless proven operational |
| A000 – Portal–Terminal | Operational status unknown | Investigate |
| X106 | Contains three route variants | Preserve and investigate all variants |
| C017 | Circular route | Preserve as a circular route |
| C018 | Bodeguita–Torices | Include after validation |
| A118 | Ciudadela La Paz–Portal | Include after validation |

## 6. Transport operators

The API identifies three transport operators.

| Operator ID | Operator |
|---|---|
| 10297 | Transcaribe Operador |
| 10296 | TRANSAMBIENTAL SAS |
| 10298 | SOCIEDAD OPERADORA DE TRANSPORTE MASIVO DE CARTAGENA – SOTRAMAC S.A.S. |

Multiple operators are associated with the same bus lines.

The recommended initial GTFS implementation is to use Transcaribe as the unified public transport agency. Operator information can be retained in source data and, where appropriate, published through `attributions.txt`.

Individual operators should not result in duplicated passenger routes or departure schedules.

## 7. Bus stops

### 7.1 Endpoint

`GET https://zn5.m2mcontrol.com.br/api/forecast/lines/load/allPoints/1343`

### 7.2 Example request

```powershell
curl.exe -i "https://zn5.m2mcontrol.com.br/api/forecast/lines/load/allPoints/1343"
```

### 7.3 Validated response

| Property | Value |
|---|---|
| HTTP status | 200 OK |
| Content type | application/json; charset=utf-8 |
| Content length | 80,052 bytes |
| Authentication | Not required for tested request |
| Test date | 2026-11-25 |
| Preliminary stop count | 646 |
| Preliminary unique stop names | 626 |

### 7.4 Example response

```json
{
  "_id": "658dda9ea5ba2d1568a6baa3",
  "id": 242085,
  "name": "13 de Junio Tv69A No 64B-14",
  "latLng": {
    "lat": 10.402819,
    "lng": -75.484697
  }
}
```

### 7.5 Data model

| Field | Description | GTFS field |
|---|---|---|
| `_id` | MongoDB stop identifier | Internal source mapping |
| `id` | Numeric stop identifier | `stop_id` |
| `name` | Stop name | `stop_name` |
| `latLng.lat` | Latitude | `stop_lat` |
| `latLng.lng` | Longitude | `stop_lon` |

### 7.6 Stop validation

The preliminary analysis indicates that the starting and ending stops of the route variants can be linked to the stop dataset.

Duplicate stop names must not automatically be merged. They may represent different directions, platforms or boarding locations.

The dataset also contains individual BRT platform identifiers, including names such as:

- Bazurto A1
- Bazurto A2
- Cuatro Vientos B2
- La Castellana B2
- Patio Portal A3
- Patio Portal B4
- Patio Portal C3
- Patio Portal D5

These records may support station grouping using `parent_station` and `location_type` in GTFS after additional validation.

## 8. Route geometry

### 8.1 Endpoint

`/forecast/lines/load/pattern/{lineId}/1343` (`lineId` = `allLines[].id`)

### 8.2 Example request

```powershell
curl.exe -s "https://zn5.m2mcontrol.com.br/api/forecast/lines/load/pattern/9892/1343"
```

### 8.3 Validated response (2026-11-25)

A JSON array with one object per route variant of the line:

```json
[
  {
    "id": 20337,
    "type": "U. Tecnologica",
    "polyLine": [
      {"lat": 10.37068386310623, "lng": -75.46589938929544},
      {"lat": 10.3706347014851, "lng": -75.46597034545246}
    ]
  }
]
```

| Field | Description | GTFS |
|---|---|---|
| `id` | Route variant (`id_migracao`) | `shape_id` |
| `type` | Destination of the variant | candidate for `trip_headsign` |
| `polyLine[].lat`, `.lng` | Coordinates, in array order (not an encoded polyline) | `shape_pt_lat`, `shape_pt_lon`, `shape_pt_sequence` |

- One request returns all variants of the line.
- For A102 the geometry runs **against** the direction of travel. The
  generator checks the direction against `startPoint`, `endPoint` and the stop
  order from `bustop`, and reverses where needed.
- `shape_dist_traveled` and the variant length come from the geometry itself;
  `kmTrajeto` and `porcentagemTrajeto` are a check.

### 8.4 GTFS implementation

These geometries are used directly for `shapes.txt`. Routing over the OSM road
network (issue #28) is only a fallback for missing or invalid geometries.

## 9. Stops per route variant

### 9.1 Endpoint

`/forecast/lines/load/bustop/{patternId}/1343`

### 9.2 Example request

```powershell
curl.exe -i "https://zn5.m2mcontrol.com.br/api/forecast/lines/load/bustop/659b60837b35aa4792d76a9f/1343"
```

### 9.3 Expected data

- Stops served by the route variant
- Stop identifiers
- Stop sequence
- Possibly additional route-specific stop information

The returned stop order must be verified.

### 9.4 Validated response (2026-11-25)

`bustop/20337/1343` (A102 IDA, Portal - U. Tecnológica, `kmTrajeto` 3.9)
returns a JSON array of 10 stops with the fields:

| Field | Description |
|---|---|
| `_id` | MongoDB stop identifier |
| `id` | Numeric stop identifier (same as in `allPoints`) |
| `name` | Stop name |
| `latLng.lat`, `latLng.lng` | Position |
| `porcentagemTrajeto` | Position along the route variant in percent (8.58 ... 84.51) |

The array is in route order (ascending `porcentagemTrajeto`). The distance of
a stop along the variant is `porcentagemTrajeto / 100 * kmTrajeto`, which gives
`shape_dist_traveled` and, with a speed assumption, travel times for
`stop_times.txt`. There is no time field. The start and end stop (here Patio
Portal and U. Tecnológica) are not in the list; they are the variant's
`startPoint` and `endPoint` in `allLines`.

The stops match the open data (Terrazas de Granada Eje 6, Colegio Castillo,
Entrada Amarilo, Villa del Sol, U. San Buenaventura, CC. San Fernando, Viper,
Entrada Simón Bolívar, Cervecería Águila, Tenaris), with their own coordinates.

This endpoint is essential for generating `stop_times.txt` and linking route variants to their corresponding stops.

## 10. Scheduled departures

### 10.1 Endpoint

`/forecast/lines/load/departure/{patternId}/1343`

### 10.2 Example request

```powershell
curl.exe -i "https://zn5.m2mcontrol.com.br/api/forecast/lines/load/departure/659b60837b35aa4792d76a9f/1343"
```

### 10.3 Research objectives

The departure endpoint should be investigated to determine whether it provides:

- Individual scheduled departures
- Departure times per route variant
- Service start and end times
- Weekday schedules
- Saturday schedules
- Sunday schedules
- Public holiday schedules
- Frequency information
- Scheduled travel times
- Intermediate stop passage times
- Schedule validity periods

If individual departures are available, explicit trips should be generated rather than converting the departures into estimated frequencies.

### 10.4 Validated response (2026-11-25, a Wednesday)

`departure/{id_migracao}/1343` returns a JSON array with one object:

| Field | Description |
|---|---|
| `id_migracao` | Route variant |
| `primeiraPartida` | First departure (`HH:MM`) |
| `ultimaPartida` | Last departure |
| `partidas` | All departure times from the first stop (`HH:MM`) |

- A102 IDA (20337): 102 departures, 05:00-22:00, about every 8-9 minutes.
- A102 VUELTA (20351): 108 departures, 05:22-22:34; every 7-8 minutes in the
  peaks, 12 minutes around midday (e.g. 09:26, 09:38, 09:50, 10:02).

These are individual scheduled departures, not a frequency: the feed gets
explicit trips. There is no day type field, but the endpoint takes a
**`date` parameter** (`?date=YYYY-MM-DD`; without it: today):

| Date | Day | A102 IDA (20337) |
|---|---|---|
| 2026-11-25 | Wednesday | 102 departures, 05:00-22:00, 8-9 min in the peaks, 12 min off-peak |
| 2026-11-28 | Saturday | 53 departures, 06:00-19:00, every 15 min |
| 2026-11-29 | Sunday | none (A102 does not run on Sundays) |

**Horizon.** Departures exist for past dates and up to the end of the current
week only: on 2026-11-25, `date=2026-11-20` and `2026-11-26` answer, but
`2026-11-30`, `2026-12-02` and later are empty for every variant (one variant,
T100E, returned 115 times `"00:00"` for 2026-12-02). An empty list therefore
does not mean "no service" for dates beyond the horizon. (An earlier test of
the festivo 2026-12-08 was empty for this reason, not because of the holiday.)

**Snapshot of 2026-11-25** (`raw/m2m/`), all 46 variants (A000 test lines left
out), dates 2026-11-20 (Fri), 2026-11-23 (Mon), 2026-11-26 (Thu), 2026-11-21
(Sat), 2026-11-22 (Sun), 2026-11-02 and 2026-11-16 (festivos, Mondays):

| Day | Departures (all variants) |
|---|---|
| Mon, Thu, Fri | 5,990 each, identical per variant |
| Saturday | 3,952 |
| Sunday | 2,642 |
| Festivo 2026-11-02 | 2,642, identical to Sunday |
| Festivo 2026-11-16 | 2,710: the Sunday schedule plus A111 (10) and the X106 extension (58) with their weekday departures |

So: one weekday, one Saturday and one Sunday/holiday schedule. Not on
Saturday nor Sunday: A111, C017, C018, the X106 extension; not on Sunday:
A102, T100E. On 2026-11-16 the API still had A111 and the X106 extension
running, while Transcaribe announced they would not run (news 10211); the API
holds the base schedule, not such announcements. Holidays beyond the horizon
are modelled as Sunday service in `calendar_dates.txt` (Colombian festivos),
with A111, C017, C018 and the X106 extension not running.

## 11. Additional endpoints

### 11.1 Lines serving a stop

`/forecast/lines/load/linesFromBusstop/{stopId}/1343`

Example:

```powershell
curl.exe -i "https://zn5.m2mcontrol.com.br/api/forecast/lines/load/linesFromBusstop/658dda9ea5ba2d1568a6ba45/1343"
```

This endpoint may be useful for independently validating the relationship between bus stops and route variants.

### 11.2 Arrival predictions

`/forecast/lines/load/forecast/lines/fromPoint/{stopId}/1343`

Example:

```powershell
curl.exe -i "https://zn5.m2mcontrol.com.br/api/forecast/lines/load/forecast/lines/fromPoint/658dda9ea5ba2d1568a6ba45/1343"
```

Potential future use: GTFS Realtime TripUpdates.

### 11.3 Route-related predictions

`/forecast/lines/load/all/forecast/{id1}/{id2}/1343`

The meaning of the two identifiers has not yet been established.

### 11.4 Nearby stops

`/forecast/lines/load/busStop/{lat}/{lon}/1343?radiusInMeters={radius}`

Example:

```powershell
curl.exe -i "https://zn5.m2mcontrol.com.br/api/forecast/lines/load/busStop/10.395/-75.472/1343?radiusInMeters=500"
```

This endpoint could be used to validate geographical stop searches.

**Validated 2026-11-25** (`busStop/10.3956/-75.4724/1343?radiusInMeters=400`):
24 stops with `_id`, `id`, `name`, `latLng`. Unlike `allPoints`, it includes
the start and end points of the route variants (`allLines[].trajetos[].startPoint`
/ `endPoint`), e.g. 242523 Patio Portal D3, 242635 Patio Portal D4, 242409
Patio Portal D2, as well as depots (GARAGE TA, Patio Transambiental, Patio
Transcaribe). `fetch_m2m.py --terminals` uses it to fetch all start and end
points into `raw/m2m/terminals.json`.

### 11.5 Forecast endpoints (validated 2026-11-25)

Not used now (no realtime, section 0); recorded for later and for the
running-time idea below.

- `forecast/lines/fromPoint/{stopId}/1343`: predictions for all lines at a stop
  (`stopId` = numeric id from `allPoints`, e.g. 242521 Patio Portal A1).
- `all/forecast/{stopId}/{id_migracao}/1343`: predictions for one variant at a
  stop (e.g. 242283 Tenaris, 20337 A102 IDA).

Both return a JSON array (empty = no predictions) of:

| Field | Description | GTFS Realtime |
|---|---|---|
| `codVehicle` | Public vehicle number (e.g. `TC33009`) | `vehicle.label` |
| `idVeiculo` | Internal vehicle id | `vehicle.id` |
| `arrivalTime` | Expected arrival, probably in minutes from now | `stop_time_update.arrival` |
| `pointLocationId` | Stop id | `stop_time_update.stop_id` |
| `busServiceId`, `busServiceNumber`, `nameLine` | Line | `trip.route_id` |
| `patternId`, `patternName`, `destination` | Route variant | link to the static trips |
| `latLng` | Probably the current vehicle position | `position` |
| `acessibilidade` | Accessibility flag, meaning unknown | |
| `trajetos[].idString` | MongoDB variant id | |

No GPS timestamp and no reference to a scheduled trip. Open: unit of
`arrivalTime` (probably minutes), meaning and age of the position, prediction
horizon, refresh interval, a central endpoint for all vehicles.

**Possible use for the static feed (running times, issue #25):** the predicted
arrival of the same vehicle (`idVeiculo`) at successive stops of a variant,
taken at the same moment, gives the predicted running time between those
stops. A few samples per variant and time of day would give a running-time
profile to check (or replace) the GraphHopper estimate. Minute resolution and
an unknown prediction model limit the precision.

## 12. Fare information

A separate JSON resource was identified in the application configuration.

URL:

https://m2m-web-teste.s3.us-east-1.amazonaws.com/cargas/1343/valorTarifa.json

Example request:

```powershell
curl.exe -i "https://m2m-web-teste.s3.us-east-1.amazonaws.com/cargas/1343/valorTarifa.json"
```

Validated 2026-11-25 and stored in `raw/m2m/valorTarifa.json`: one field,
`{"valor" : "$ 3.900,00"}`, the general fare as display text. It matches the
fare in force since 23 Jan 2026. It has no reduced fare (tarifa diferencial
2.900 COP), fare media or transfer rules, so `fare_products.txt` /
`fare_media.txt` / `fare_transfer_rules.txt` still come from Transcaribe's own
information (issue #29). The bucket is named `m2m-web-teste`, so the file may not
be maintained.

Potential GTFS integration:

- `fare_attributes.txt`
- `fare_rules.txt`
- `fare_products.txt`
- `fare_media.txt`
- `fare_leg_rules.txt`

The appropriate fare model depends on the returned information and the supported GTFS fare specification.

Currency: COP.

## 13. News and service information

A news endpoint was identified:

https://meuonibusteste.m2mfrota.com.br/clientes/transcaribe/?json=1

Potential uses include:

- Temporary route changes
- Service interruptions
- New routes
- Fare changes
- Timetable changes
- GTFS Realtime Service Alerts

Availability and response structure remain unverified.

## 14. Geocoding services

The following additional services were identified:

- `https://sso-admin.m2mcontrol.com.br/places/api/`
- `https://nominatim.sinopticoplus.com/nominatim/search`

These services appear to support geographical search functionality within the application.

They are not required for the initial GTFS generator.

## 15. Application data models

The following relevant classes were identified during the initial APK analysis.

| Class | Expected purpose |
|---|---|
| `LinhaOnibus` | Bus line |
| `PontoOnibus` | Bus stop |
| `Trajeto` | Route variant |
| `PolylinePoint` | Route geometry coordinate |
| `Coordenada` | Geographical coordinate |
| `DepartureHour` | Scheduled departure |
| `PrevisaoTrajeto` | Route prediction |
| `Itinerary` | Journey itinerary |
| `ItineraryDetailItem` | Journey details |
| `ValorTarifa` | Fare information |
| `MeuOnibusWS` | Web service client |
| `PontoDAO` | Local stop storage |
| `AppDataBase` | Local application database |

Additional DEX analysis may help determine the precise endpoint parameters, HTTP methods and response schemas.

## 16. Identifier strategy

The API uses both numeric identifiers and MongoDB identifiers.

| Entity | Numeric identifier | MongoDB identifier |
|---|---|---|
| Route | `id` | `idLinha` |
| Route variant | `id_migracao` | `id` / `_id` |
| Stop | `id` | `_id` |

Both identifier types should be retained in the raw and normalized source datasets.

Recommended initial GTFS identifiers:

| GTFS field | Source |
|---|---|
| `agency_id` | `transcaribe` |
| `route_id` | Numeric line ID |
| `route_short_name` | `numero` |
| `route_long_name` | Normalized line name |
| `stop_id` | Numeric stop ID |
| `shape_id` | Route variant ID |
| `direction_id` | Derived from validated route direction |
| `trip_id` | Stable combination of route variant, service and departure |

The stability of identifiers should be monitored over multiple API snapshots.

## 17. GTFS coverage assessment

| GTFS file | Data source | Status |
|---|---|---|
| `agency.txt` | Transcaribe organization information | Available |
| `routes.txt` | `allLines` | Validated source |
| `stops.txt` | `allPoints` | Validated source |
| `shapes.txt` | `pattern` | Endpoint identified |
| `trips.txt` | `allLines` and `departure` | Partially available |
| `stop_times.txt` | `bustop` and `departure` | Research required |
| `calendar.txt` | Departure schedules | Research required |
| `calendar_dates.txt` | Departure schedules and Colombian holidays | Research required |
| `frequencies.txt` | Departure schedules, if applicable | Research required |
| `fare_attributes.txt` | Fare JSON | Endpoint identified |
| `fare_rules.txt` | Fare JSON | Endpoint identified |
| `attributions.txt` | Transport operator information | Available |
| `transfers.txt` | Station and transfer analysis | Research required |
| `feed_info.txt` | Generator configuration | Can be generated |

## 18. GTFS Realtime potential

| GTFS Realtime component | Assessment |
|---|---|
| TripUpdates | Potentially available through arrival predictions |
| VehiclePositions | No dedicated endpoint confirmed |
| ServiceAlerts | Potentially available through news information |

GTFS Realtime implementation should be treated as a separate development phase.

A reliable mapping between source route identifiers, scheduled trips and real-time observations must first be established.

## 19. Recommended repository structure

```text
gtfs-cartagena/
├── README.md
├── docs/
│   └── mib-us-transcaribe-api.md
├── research/
│   └── m2m-api/
│       ├── endpoints.json
│       ├── samples/
│       └── validation/
├── data/
│   ├── raw/
│   │   └── m2m/
│   │       ├── allLines.json
│   │       ├── allPoints.json
│   │       ├── patterns/
│   │       ├── bustops/
│   │       ├── departures/
│   │       └── fares.json
│   └── normalized/
├── scripts/
│   ├── fetch_api.py
│   ├── normalize_data.py
│   ├── validate_source.py
│   └── generate_gtfs.py
├── requirements.txt
└── .github/
    └── workflows/
        ├── fetch-data.yml
        ├── generate-gtfs.yml
        └── release.yml
```

## 20. Data collection strategy

The API collector should:

1. Retrieve all bus lines.
2. Retrieve all bus stops.
3. Extract all unique route variant identifiers.
4. Retrieve geometry for each route variant.
5. Retrieve stops for each route variant.
6. Retrieve departure schedules for each route variant.
7. Retrieve fare information.
8. Preserve original API responses.
9. Record collection timestamps, HTTP statuses and checksums.
10. Compare the retrieved dataset with previous snapshots.
11. Report added, removed and modified routes.
12. Validate references between routes, route variants and stops.

Requests should use reasonable rate limits, caching, retries and exponential backoff.

API credentials must not be committed to the repository. Public accessibility of an endpoint does not automatically establish permission to redistribute its data; applicable data licensing and usage conditions should also be investigated.

## 21. Validation strategy

The generated data should be checked for:

- Duplicate identifiers
- Missing stop names
- Invalid GPS coordinates
- Missing route variants
- Missing route geometries
- Missing or incorrect stop sequences
- Stops located too far from their route geometry
- Invalid departure times
- Missing service calendars
- Inactive and test routes
- Incorrect circular route handling
- Duplicate services caused by multiple operators

The resulting GTFS feed should be validated using the MobilityData GTFS Validator before publication.

The API stop dataset should additionally be compared with the previously identified Cartagena open data dataset `nemj-z89t` and OpenStreetMap.

## 22. Research checklist

- [x] Obtain Android application
- [x] Identify primary API server
- [x] Identify Transcaribe customer ID
- [x] Identify API endpoint paths
- [x] Validate unauthenticated route endpoint
- [x] Validate unauthenticated stop endpoint
- [x] Identify transport operators
- [x] Identify route variant IDs
- [x] Validate route geometry endpoint (`pattern/{lineId}`; A102 geometry reversed)
- [x] Validate route stop sequence endpoint
- [x] Validate departure endpoint
- [x] Confirm identifier types required by each endpoint (`id_migracao`)
- [x] Identify service day categories (weekday, Saturday, Sunday/holiday; horizon: end of the current week)
- [ ] Identify scheduled travel times
- [x] Validate fare JSON (general fare only)
- [ ] Investigate A000 routes
- [ ] Investigate additional X106 route variant
- [ ] Validate BRT station and platform relationships
- [x] Investigate data licensing
- [x] Implement API collector
- [x] Implement GTFS generator
- [x] Validate GTFS feed
- [x] Publish initial GTFS release
- [ ] Investigate GTFS Realtime support (not now, see section 0)

## 23. Conclusion

The Mi Bus Transcaribe application provides a promising direct data source for the Transcaribe public transport network.

The initial research identified:

- 26 bus line records
- 50 route variants
- 646 bus stops
- Three associated transport operators
- Route geometry endpoints
- Route-specific stop endpoints
- Scheduled departure endpoints
- Real-time prediction endpoints
- A separate fare information resource

The route and stop endpoints have been successfully tested without authentication.

If route geometry, ordered stops and departure schedules are available through the remaining endpoints, the M2M Control API could become the primary data source for the ColombiaTransit Cartagena GTFS generator.

The `bustop` and `departure` endpoints were validated with route A102 on
2026-11-25: ordered stops with their position along the route, and individual
scheduled departures. The `departure` endpoint takes a `date`
parameter (past dates and up to the end of the current week); weekday,
Saturday and Sunday/holiday schedules were collected on 2026-11-25. `pattern` takes the line id and returns
the geometry of all variants as plain coordinates. Next: a collector that
stores one snapshot of all endpoints, with departures for a weekday, a
Saturday, a Sunday and the holidays of the feed period, in `raw/m2m/` (done); licensing settled 2026-11-26.

The inventory counts are preliminary results from the preceding analysis and should be independently reproduced by the API collector before publication.