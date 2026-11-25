# GTFS design – Transcaribe static feed (v1)

Built by `scripts/build_gtfs.py` from the Mi Bus Transcaribe API snapshot
(`raw/m2m/`, see `docs/mibus-transcaribe-api.md`), the GraphHopper running
times (`data/running_times.csv`) and the holiday calendar
(`scripts/gtfs_calendar.py`). One-off build; no daily refresh.

The model is chosen so that GTFS-Realtime can be added later from the API's
forecast endpoints without changing the static identifiers.

## Identifiers (stable, from the API)

| GTFS | Value | API field it matches (forecast endpoints) |
|---|---|---|
| `agency_id` | `transcaribe` | |
| `route_id` | numeric line id, e.g. `9892` | `busServiceId` |
| `shape_id` | route variant `id_migracao`, e.g. `20337` | `patternId` |
| `stop_id` | numeric stop id, e.g. `242283` (also `stop_code`) | `pointLocationId` |
| `service_id` | `weekday`, `saturday`, `sunday` | |
| `trip_id` | `<id_migracao>_<service_id>_<HHMM>` of the departure from the first stop (suffix `_2` on a repeated minute), e.g. `20337_weekday_0508` | `patternId` + nearest scheduled departure |
| `parent_station` | `st_<name>`, e.g. `st_bazurto` (our own; the API has no station objects) | |

A rebuild from a new snapshot keeps the same ids for the same lines, variants,
stops and departures, so realtime matching and links from other systems keep
working. Vehicles (`idVeiculo`, `codVehicle`) are not in the static feed; they
go into `VehiclePositions` / `TripUpdates.vehicle` later.

To match a realtime prediction to a trip later: `patternId` gives the variant
(`shape_id`), the service day gives the `service_id`, and the departure from
the first stop closest to the vehicle's progress gives the `trip_id`. There is
no `block_id` (the API does not say which vehicle runs which trips).

## Files

- `routes.txt`: 24 lines (A000 test lines left out; C016 is not in the API).
  `route_desc` = Troncal / Pretroncal / Alimentadora / Complementaria from the
  first letter of the number; colours per type.
- `stops.txt`: every stop of a variant (`bustop`) with the API name and
  position, plus the start and end points of the variants. Those are not in
  `allPoints`, but the nearby-stops endpoint (`busStop/{lat}/{lon}`) returns
  them with name and position: `fetch_m2m.py --terminals` stores them in
  `raw/m2m/terminals.json`. Without that file they take the end of the geometry
  and a name from the variant's destination or the open data. Names ending in a vagón
  code ("Bazurto A1", "Patio Portal C2") are platforms of a trunk station:
  `location_type=1` parent from `data/stops.csv` (OSM position, accented
  name), `platform_code` = the code. The API gives every vagón its own
  position, so the A/B order no longer has to be assumed.
- `shapes.txt`: the API geometry per variant, turned round where it runs
  against the direction of travel (all variants but the circular C017), with
  `shape_dist_traveled` in metres.
- `trips.txt`: one trip per scheduled departure (no `frequencies.txt`: the API
  has individual departures). `direction_id` 0 = IDA/CIRCULAR, 1 = VUELTA.
  `trip_headsign` = destination without vagón code.
- `stop_times.txt`: first stop at the scheduled departure (`timepoint=1`), the
  others estimated (`timepoint=0`): GraphHopper bus-profile running time per
  leg along the geometry; where GraphHopper left the line (distance >25% off,
  e.g. La Popa - Chambacú) the leg's length at the variant's median
  GraphHopper speed; plus dwell 20 s at street stops, 30 s at station
  platforms. `shape_dist_traveled` per stop.
- `calendar.txt` / `calendar_dates.txt`: three services over the feed period
  (default: build day + 182 days); Colombian holidays (`holidays` package)
  switch to `sunday`.
- `attributions.txt`: the operators per route (Transcaribe Operador,
  Transambiental, Sotramac), `is_operator=1`.
- `feed_info.txt`: publisher ColombiaTransit, contact via GitHub issues.
- Fares (Fares v2), one flat fare per leg:
  - `fare_media.txt`: Tarjeta TransCaribe (`fare_media_type=2`), contactless
    bank card / Visa (`3`).
  - `rider_categories.txt`: `general` (default) and `diferencial` (students,
    older people, disability; personalised card).
  - `fare_products.txt`: `pasaje` 3,900.00 COP on both media (from
    `raw/m2m/valorTarifa.json`, checked against Decreto 017 de 2026), and
    2,900.00 COP for `diferencial` on the card only (Decreto 0176 de 2026).
  - `fare_leg_rules.txt`: every leg costs `pasaje`.
  - No `fare_transfer_rules.txt` yet: the rule of four transfers in the same
    direction within 90 minutes is from 2020 (news 1096) and not confirmed.

## Known limits

- Running times are estimates. Totals for a few routes against outside
  figures: T101 Portal - Centro 38 min here, 24 min in Moovit, ~30 min one way
  from Transcaribe's "about one hour round trip"; X101 50-59 min here, 35-39
  min in Moovit. The estimates are on the long side; calibrate with the
  forecast endpoints (sampling) or a few timed trips.
- Announced changes (detours, suspended routes on special days) are not in the
  API's base schedule and not in the feed.
- One stop (X101 "Frente I.E. Las Gaviotas") lies 137 m from its geometry.
- Licensing of the API data is not settled: ask Transcaribe / M2M Control
  before publishing the feed.

## Validation

MobilityData GTFS Validator 7.1.0 (country `co`), build of 2026-11-25:
no errors; 1 warning (`stop_too_far_from_shape_using_user_distance`, the stop
above).
