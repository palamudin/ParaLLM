# Blender/GIS Proof Log

## 2026-06-02 - Kotor Terrain/Road Proof

### Fact

- Blender 5.1.2 is installed at `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`.
- `specialization/scripts/fetch_osm_terrain.py` generated `specialization/output/data/terrain_roads_dataset.json`.
- `specialization/scripts/blender_generate_terrain_roads.py` generated `specialization/output/blender/terrain_road_network_proof.blend`.
- Preview render exists at `specialization/output/reports/terrain_road_network_preview_0001.png`.
- Dataset summary:
  - area: Kotor, Montenegro
  - roads: 344
  - buildings in normalized dataset: 615
  - generated Blender building massings: 300
  - junction pads: 30
  - sampled elevation range: -7 m to 383 m

### Provider Behavior

- Overpass succeeded through `https://overpass-api.de/api/interpreter`.
- Open-Meteo elevation returned HTTP 429 during this run.
- Fetcher fell back to Open-Elevation successfully.
- OpenTopoData SRTM90m was also tested for the center coordinate and responded successfully, but was not used for the final dataset.

### Blender Proof Behavior

- Terrain mesh, road curves, junction cylinders, and building massing objects are created in Blender.
- Roads are currently generated as 3D curve splines with bevel depth.
- Camera is orthographic and sized from OSM/building bounds.
- Materials are node-backed for preview legibility.

### Para Pressure

Para's commander packet recommended keeping BlenderGIS optional, staying source-first, and validating native Blender curves/API before claiming Blender 5.x specificity.

The artifact pressure pass identified:

- vertical terrain banding in the preview as an unresolved validation issue,
- a 615 input building footprint versus 300 generated massing count that must be described as an intentional cap or treated as data loss,
- coarse road geometry: 100 two-point roads and 241 roads with five points or fewer,
- the need to split true intersections before claiming road-network quality.

### Next Test

Run a focused steep-corridor A/B:

- baseline: current bevel-curve roads,
- variant: terrain-conforming roadbed mesh/ribbon,
- freeze buildings and global terrain,
- render close-up and top-down views,
- compare roadbed continuity, junction continuity, and whether terrain banding is geometry or shading.

## 2026-06-02 - Kotor Corridor A/B Proof

### Fact

- `specialization/scripts/blender_corridor_ab.py` generated `specialization/output/blender/kotor_corridor_ab.blend`.
- Preview render exists at `specialization/output/reports/kotor_corridor_ab_preview_0001.png`.
- Report exists at `specialization/output/reports/kotor_corridor_ab_report.json`.
- Selected corridor:
  - OSM way: `165439817`
  - highway class: `residential`
  - point count: 13
  - length: 123.03 m
  - relief: 43.0 m
  - mean relief grade: 0.3495
- Generated local comparison context:
  - A panel: curve road with bevel depth.
  - B panel: terrain-following roadbed ribbon mesh.
  - nearby roads: 16
  - nearby buildings: 51

### Engineering Result

- The A/B artifact clearly separates the old curve-only representation from a first roadbed ribbon representation.
- The B ribbon follows sampled terrain and visually reads as a road surface rather than only a centerline.
- The scene is useful as a blocker-finding artifact for Blender/GIS specialization work.

### Current Limit

- The ribbon does not cut, flatten, or grade the terrain underneath it.
- No true road graph split is performed at intersections in this proof.
- The selected corridor is steep enough to expose vertical behavior, but the DEM source remains too coarse for final-grade terrain.

### Next Test

Add graph splitting and terrain flattening under the same selected corridor, then compare:

- baseline curve,
- terrain-following ribbon,
- flattened/cut roadbed ribbon,
- junction continuity near intersecting roads.

### Para Pressure

Para's compact commander review accepted the artifact as a valid incremental A/B proof with medium confidence.

Top pressure from Para:

- The artifact proves comparison workflow and corridor selection, not topology correctness.
- The current roadbed ribbon does not prove intersection splitting or cut/flatten behavior.
- DEM banding may be cosmetic, but it may also hide road/terrain contact problems.

Recommended next check from Para:

Add graph splitting and flatten the terrain under the roadbed ribbon on the same selected corridor, then rerender the comparison.

## 2026-06-02 - Kotor Corridor A/B/C Proof

### Fact

- `specialization/scripts/blender_corridor_abc.py` generated `specialization/output/blender/kotor_corridor_abc.blend`.
- Preview render exists at `specialization/output/reports/kotor_corridor_abc_preview_0001.png`.
- Report exists at `specialization/output/reports/kotor_corridor_abc_report.json`.
- The proof compares three panels:
  - A: curve road with bevel depth.
  - B: terrain-following roadbed ribbon mesh.
  - C: terrain-flattened roadbed ribbon with first-order graph-node junction geometry.
- Selected corridor remains OSM way `165439817`.
- Junction candidates detected: 3.
- Junction type: near-endpoint graph nodes.
- Mid-segment crossing splits detected for this corridor: 0.
- Split corridor point count: 13.
- Junction pads generated: 3.
- Connector stubs generated: 4.
- Surface-overlap continuity pass: true.
- Merged-mesh connectivity tested: false.

### Engineering Result

- C is a concrete local step beyond A/B because the terrain under the selected roadbed is modified by a flattening profile.
- The script now detects exact segment crossings and near-endpoint graph nodes, then reports the detected junction candidates.
- The C panel now creates first-order pad-and-stub mesh geometry at the detected graph nodes.
- The generated report validates surface overlap between pads and connector stubs for all detected junction candidates.
- The selected Kotor corridor exposes endpoint graph-node work rather than crossroad cutting work.

### Current Limit

- Pad-and-stub geometry is not yet validated as continuous or traversable.
- Current continuity validation is surface overlap only; it does not prove shared-vertex, boolean-unioned, or traversable road topology.
- Flattening is local to one corridor and is not propagated into the surrounding road graph.
- The top-down preview does not fully validate slope/grade smoothness; a profile or oblique view is needed for that.

### Para Pressure

Para returned a caution verdict with medium confidence.

Top pressure from Para:

- C proves local terrain flattening plus split-marker placement.
- C does not prove connected road-graph topology.
- Near-endpoint candidates do not exercise the hardest branching case.

Recommended next check from Para:

Convert the split markers into actual connected junction geometry and verify connectivity on this corridor.

After the marker-to-geometry upgrade, Para returned another caution verdict with medium confidence.

Top pressure from the upgraded review:

- The strongest valid claim is local first-order junction geometry.
- Pad/stub existence does not prove continuity or traversability.
- Do not claim full topology or connectivity until continuity is validated.

Recommended next check from Para after the upgrade:

Validate continuity through the generated pads/stubs, then treat bend and grade smoothing as the follow-on step.

### Next Test

Build merged junction geometry at the three graph nodes:

- replace overlapping pad/stub surfaces with shared-vertex or boolean-unioned meshes,
- generate a top-down and oblique/profile render,
- report continuity gaps and grade discontinuities.

## 2026-06-02 - San Francisco Corridor A/B/C Proof

### Fact

- `specialization/scripts/fetch_san_francisco_terrain.py` generated `specialization/output/data/san_francisco_terrain_roads_dataset.json`.
- `specialization/scripts/blender_corridor_abc.py` generated `specialization/output/blender/san_francisco_corridor_abc.blend`.
- Top-down preview exists at `specialization/output/reports/san_francisco_corridor_abc_preview_0001.png`.
- Oblique C-panel preview exists at `specialization/output/reports/san_francisco_corridor_abc_oblique_.png`.
- Report exists at `specialization/output/reports/san_francisco_corridor_abc_report.json`.
- Dataset summary:
  - roads: 911
  - buildings: 1,682
  - endpoint junctions: 212
  - elevation provider: Open-Elevation
- Selected corridor:
  - OSM way: `1253937430`
  - name: Union Street
  - highway class: tertiary
  - point count: 16
  - length: 292.09 m
  - relief: 66.0 m
  - mean relief grade: 0.226
  - max absolute segment grade: 0.3276
  - elevation range: 28.0 m to 94.0 m
- Generated local geometry:
  - nearby roads: 23
  - nearby buildings: 59
  - junction candidates: 2
  - junction pads: 2
  - connector stubs: 2
  - surface-overlap continuity: true

### Road Data Context

- The executable proof uses OSM geometry through Overpass.
- DataSF exposes official street centerline data with `cnn` identifiers and line geometry.
- OSM-to-DataSF `cnn` reconciliation is not implemented yet.

### Engineering Result

- San Francisco is a materially harder terrain-undulation test than the Kotor corridor because the selected Union Street corridor has 66 m relief over 292.09 m.
- The oblique render makes the roadbed slope behavior visible instead of relying on top-down inspection only.
- The current generator can process a dense urban-grid sample and still generate a readable A/B/C proof.

### Current Limit

- Surface-overlap continuity does not prove shared-vertex or boolean-unioned mesh connectivity.
- The selected corridor exercises endpoint attachment, not crossing-heavy topology.
- City-scale road-network correctness is not established.
- Official DataSF centerline conformance is only identified as a validation lane.

### Para Pressure

Para returned a caution verdict.

Top pressure from Para:

- Treat this as a corridor-local terrain and attachment proof, not network correctness.
- The next blocker is topology-preserving junction connectivity.
- The proof uses OSM plus Open-Elevation; official city-network conformance needs DataSF reconciliation.

### Next Test

Build topology-preserving junction meshes:

- replace overlap-only pads/stubs with shared-vertex or boolean-unioned meshes,
- run the same validation on at least one endpoint-heavy corridor and one crossing-heavy corridor,
- start an OSM-to-DataSF centerline reconciliation check for Union Street.
