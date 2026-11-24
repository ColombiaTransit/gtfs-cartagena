# OpenStreetMap exports

Data © OpenStreetMap contributors, available under the
[Open Database License (ODbL)](https://www.openstreetmap.org/copyright).

`scripts/fetch_osm.py` (workflow *Fetch OSM data from Overpass*, needs the
`OVERPASS_URL` secret) exports all files below from our own Overpass server;
the first two were exported by hand from Overpass Turbo on 2026-11-08. The
exact queries are in the script.

- `overpass_stops.json`, `overpass_routes.json`: see below.
- `roads.geojson.gz`: drivable roads (motorway to service, busway), one
  LineString per way with `nodes` (OSM node ids, for routing) and the tags
  highway, name, ref, oneway, junction, access, bus, psv, lanes, maxspeed.
- `pois.csv`: named amenities, shops, leisure, tourism, offices, healthcare,
  historic sites, named buildings and neighbourhoods, with their centre;
  stops are often named after these.

## overpass_stops.json

Bus stops, platforms, stop positions and stations in the Cartagena area.

```
[out:json][timeout:180];
(
  node["highway"="bus_stop"](10.28,-75.58,10.52,-75.40);
  nwr["public_transport"~"^(platform|stop_position|station)$"](10.28,-75.58,10.52,-75.40);
  nwr["amenity"="bus_station"](10.28,-75.58,10.52,-75.40);
  relation["type"="route"]["route"~"^(bus|trolleybus)$"](10.28,-75.58,10.52,-75.40);
  relation["type"="route_master"]["route_master"~"^(bus|trolleybus)$"](10.28,-75.58,10.52,-75.40);
);
out center tags;
```

## overpass_routes.json

Transcaribe route relations with their members and way geometry.

```
[out:json][timeout:180];
relation["type"="route"]["route"="bus"]["operator"~"ra?n?s?caribe",i]
  (10.28,-75.58,10.52,-75.40)->.r;
.r out body;
node(r.r);
out;
way(r.r);
out geom;
```

X103 is tagged `operator=Trasncaribe S.A.`, which this regex misses. It was
exported separately with `["ref"="X103"]["operator"~"caribe",i]` and merged
into this file. `fetch_osm.py` uses `["operator"~"caribe",i]`.
