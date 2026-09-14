# San Francisco Road Data Notes

## Executable Proof Data

The San Francisco proof uses OpenStreetMap road/building geometry through Overpass and Open-Elevation for terrain.

Generated dataset:

- `specialization/output/data/san_francisco_terrain_roads_dataset.json`
- `specialization/output/data/san_francisco_osm_raw.json`

Dataset summary:

- Roads: 911
- Buildings: 1,682
- Junctions: 212
- Elevation provider used: Open-Elevation
- Open-Meteo was attempted first and returned HTTP 429.

## Selected Corridor

The current A/B/C proof selected Union Street as the steepest high-scoring road-class corridor in the Russian Hill / Nob Hill test box.

- OSM way: `1253937430`
- Name: Union Street
- Highway class: tertiary
- Points: 16
- Length: 292.09 m
- Relief: 66.0 m
- Mean relief grade: 0.226
- Max absolute segment grade: 0.3276
- Mean absolute segment grade: 0.2039
- Elevation range: 28.0 m to 94.0 m

## Official City Validation Lane

DataSF exposes San Francisco street-centerline data with Centerline Network Number (`cnn`) identifiers and line geometry:

- `https://data.sfgov.org/Geographic-Locations-and-Boundaries/Streets-Active-and-Retired/3psu-pn9h`
- API sample endpoint: `https://data.sfgov.org/resource/3psu-pn9h.json?$limit=1`

The proof has not yet reconciled OSM ways to DataSF `cnn` segments. That is the next official-road-data validation lane once local geometry/topology is stronger.

## Current Boundary

This is a local terrain-undulation and roadbed-attachment proof. It is not yet a city-scale or official-centerline-conformant road network proof.
