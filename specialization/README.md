# ParaLLM Specialization: Blender Terrain + Road Networks

This folder is the working specialization vault for Blender 5.x, curve-driven road networks, terrain generation, GIS ingestion, and game-environment preparation.

## Current Mission

Build enough operational knowledge and code to let ParaLLM inspect real-world geospatial data, form terrain, route roads as terrain-following curves, reason about junctions/grades/bends, and produce auditable Blender output.

## Workspace Layout

- `notes/` - research briefs, source maps, skill plans, and engineering constraints.
- `scripts/` - data fetchers, Blender generators, and checkpoint tooling.
- `para/` - ParaLLM mission prompts and response artifacts.
- `tasks/` - hourly reminder/checkpoint logs.
- `output/` - generated data, Blender files, reports, and renders.

## First Proof Status

Completed first proof on 2026-06-02 against Kotor, Montenegro.

- OSM source: Overpass `https://overpass-api.de/api/interpreter`.
- Elevation source used: Open-Elevation `https://api.open-elevation.com/api/v1/lookup`.
- Open-Meteo was attempted first and returned `429 Too Many Requests`, so the fetcher rotated to Open-Elevation.
- Dataset: `output/data/terrain_roads_dataset.json`.
- Blender scene: `output/blender/terrain_road_network_proof.blend`.
- Preview render: `output/reports/terrain_road_network_preview_0001.png`.
- Report: `output/reports/blender_generation_report.json`.

Generated proof counts:

- 344 OSM road ways.
- 615 OSM building footprints in the normalized dataset.
- 300 simplified building massings generated in Blender for the first pass.
- 30 heuristic junction pads.
- Elevation range in sampled crop: -7 m to 383 m.

Current known gaps:

- Terrain preview shows vertical banding; needs a geometry-vs-shading diagnostic.
- Roads are curve centerlines with bevel depth, not true roadbed ribbons.
- Junctions are endpoint-degree heuristic pads; mid-way intersection splitting is not implemented yet.
- DEM resolution is too coarse for final high-detail terrain.
- Building massing is intentionally capped for first proof; full coverage needs a stated limit or pagination rule.

## Corridor A/B Proof Status

Completed focused Kotor corridor A/B proof on 2026-06-02.

- Selected OSM way: `165439817`.
- Corridor type: residential road.
- Corridor length: 123.03 m.
- Relief across selected polyline: 43.0 m.
- Mean relief grade: 0.3495.
- Blender scene: `output/blender/kotor_corridor_ab.blend`.
- Preview render: `output/reports/kotor_corridor_ab_preview_0001.png`.
- Report: `output/reports/kotor_corridor_ab_report.json`.

What this proof establishes:

- The pipeline can select a steep real-world road corridor from the Kotor dataset.
- The same local context can be rendered as an A/B comparison.
- The baseline curve road and a terrain-following roadbed ribbon can be generated from the same source polyline.

Current known gaps:

- The roadbed ribbon follows sampled terrain but does not cut, flatten, or grade the terrain under the road.
- True graph splitting at intersections is not implemented in the A/B proof.
- DEM banding remains visible because the current elevation source is coarse.
- Road engineering rules are still heuristic; this is a topology proof, not a final terrain-road solver.

Next concrete test:

Add graph splitting and terrain flattening under the selected roadbed ribbon, then re-render the same corridor with roadbed continuity and junction continuity checks.

## Corridor A/B/C Proof Status

Completed focused Kotor corridor A/B/C proof on 2026-06-02.

- Generator: `scripts/blender_corridor_abc.py`.
- Blender scene: `output/blender/kotor_corridor_abc.blend`.
- Preview render: `output/reports/kotor_corridor_abc_preview_0001.png`.
- Report: `output/reports/kotor_corridor_abc_report.json`.

Generated comparison:

- A: curve road with bevel depth.
- B: terrain-following roadbed ribbon mesh.
- C: terrain-flattened roadbed ribbon with first-order graph-node junction geometry.

New facts from the A/B/C proof:

- The selected corridor has 3 detected junction candidates.
- All detected candidates are near-endpoint graph nodes.
- This corridor has no detected mid-segment crossing splits.
- The split corridor point count remains 13 because the detected junctions align with existing corridor nodes.
- C generates 3 junction pads and 4 connector stubs.

What this proof establishes:

- C is a real local geometry step beyond A/B: roadbed terrain flattening, junction pads, and connector stubs are now generated from the same corridor facts.
- Surface-overlap continuity passes for all 3 generated junction pads.
- The proof is still local to one corridor and does not establish connected road-graph topology.
- Merged-mesh connectivity is not yet tested.

Next concrete test:

Replace overlapping pad/stub surfaces with shared-vertex or boolean-unioned junction meshes, then add road-rule-based bend and grade smoothing.

## San Francisco Terrain Proof Status

Completed a San Francisco A/B/C terrain-undulation proof on 2026-06-02.

- Dataset: `output/data/san_francisco_terrain_roads_dataset.json`.
- Raw OSM payload: `output/data/san_francisco_osm_raw.json`.
- Generator: `scripts/blender_corridor_abc.py`.
- Blender scene: `output/blender/san_francisco_corridor_abc.blend`.
- Top-down render: `output/reports/san_francisco_corridor_abc_preview_0001.png`.
- Oblique C-panel render: `output/reports/san_francisco_corridor_abc_oblique_.png`.
- Report: `output/reports/san_francisco_corridor_abc_report.json`.

Dataset counts:

- 911 road ways.
- 1,682 building footprints.
- 212 dataset endpoint junctions.

Selected corridor:

- OSM way: `1253937430`.
- Name: Union Street.
- Highway class: tertiary.
- Length: 292.09 m.
- Relief: 66.0 m.
- Mean relief grade: 0.226.
- Max absolute segment grade: 0.3276.

What this proof establishes:

- San Francisco gives a harsher undulation case than Kotor for the current roadbed logic.
- The A/B/C generator can process a dense urban grid and generate roadbed, pads, stubs, top-down render, and oblique render.
- Surface-overlap continuity passes for the selected local junction pads.

Current boundary:

- This is a corridor-local terrain and attachment proof, not a city-scale road-network proof.
- DataSF street centerlines are identified as the official validation lane, but OSM ways have not yet been reconciled to DataSF `cnn` segments.
- Merged-mesh junction connectivity remains untested.

## Operating Rule

No magic. Every specialization artifact should either cite a source, point to a generated output, or state that it is an assumption/prototype.
