# Para Artifact Pressure Packet - Kotor Blender Proof

- Task: `t-20260602-042428-96c02d`
- Captured: `2026-06-02T04:45:00+02:00`
- Note: Worker A timed out before an artifact was captured; commander and worker B completed.

## Commander Direction

Specialize next on intersection-aware roadbed geometry in the steep Kotor crop; keep building detail frozen until road topology and terrain continuity are validated.

## Commander Draft

[fact] `terrain_roads_dataset.json` summarizes 344 roads, 615 buildings, 30 junctions, and elevation from -7 m to 383 m, and `blender_generation_report.json` says the scene produced a terrain mesh, road curves, and building massing.
[fact] The report's own limitations point to the remaining gap: roads are still curve centerlines with bevel depth, junctions are heuristic endpoint pads, and elevation comes from a 90 m DEM.
[fact] The road geometry is still coarse: 100 roads are two-point segments and 241 have five points or fewer.
[assumption] Treat the vertical banding in `terrain_road_network_preview_0001.png` as a validation issue until a focused test proves it is structural.
[unknown] The preview alone does not tell us whether that banding is a mesh seam, a UV/material issue, or render/lighting noise.
[inference] Next concrete specialization step: split the road graph at true intersections and generate terrain-conforming roadbed/junction meshes in a dense Kotor crop, while leaving building detail unchanged for now.
[next check] Run a focused render after the split and compare junction continuity plus terrain banding against the current preview.

## Commander Pressure Points

- [fact] The preview has visible vertical banding; if it is structural, the next specialization should shift toward terrain continuity before road styling.
- [fact] `blender_generation_report.json` says 300 building massings, but `terrain_roads_dataset.json` contains 615 building features, so coverage is not fully explained.
- [fact] The road network is still coarse: 100 roads are two-point segments and 241 have five points or fewer, so topology enrichment is still needed.
- [fact] The elevation grid is coarse for steep Kotor terrain, so roadbed behavior may still be misleading until terrain resolution improves.

## Worker B Observation

[fact] The preview shows strong vertical banding across the terrain crop, and the report still flags centerline roads, heuristic junction pads, and a 90 m DEM. [inference] The next cheapest test is one steep-corridor roadbed A/B with buildings frozen.

## Worker B Benefits

- A/B bevel vs ribbon on one steep corridor.
- No new dependencies.
- Separates geometry from shading.

## Worker B Detriments

- Banding root cause stays ambiguous.
- DEM resolution may hide small cuts.
- Building coverage stays deferred.

## Evidence Gaps

- No close-up render isolates banding source.
- No counterexample proves junction coverage.
- No explanation for 300-vs-615 buildings.

## Recommended Next Test

A/B steep-corridor roadbed
