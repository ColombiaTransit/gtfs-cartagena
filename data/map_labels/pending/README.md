# Pending map labels

Labels that are done but not used yet. `scripts/match_stops.py` only reads
`data/map_labels/<route>.csv`, not this folder.

None at the moment. X105 now uses `data/map_labels/X105.csv` with the map
georeferenced directly (see `scripts/fit_map_labels.py`), so its OSM line
no longer matters.
