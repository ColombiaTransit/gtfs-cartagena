# Pending map labels

Labels that are done but not used yet. `scripts/match_stops.py` only reads
`data/map_labels/<route>.csv`, not this folder.

- `X105.csv`: 72 of 74 street stops. The X105 route relation in OSM does not
  follow the trunk (bus lane) in the outbound direction, so station Delicias A1
  lands on the return pass and the stops between there and Bocagrande get
  squeezed together. Fix the relation in OSM, re-export it, then move this
  file up one folder.
