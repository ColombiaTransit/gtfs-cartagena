# OpenStreetMap exports

Data © OpenStreetMap contributors, available under the
[Open Database License (ODbL)](https://www.openstreetmap.org/copyright).

Both files were exported by hand from Overpass Turbo on 2026-11-08.

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
into this file. Use `["operator"~"caribe",i]` for a full re-export.
