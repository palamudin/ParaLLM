# Terrain and Road Pipeline

## Baseline Pipeline

1. Select a bounded area.
2. Query OpenStreetMap through Overpass for:
   - highways,
   - building footprints,
   - place/population tags when present.
3. Query elevation samples on a grid.
4. Project lat/lon to local meters with an equirectangular approximation.
5. Generate terrain mesh.
6. Generate road curves:
   - centerline from OSM way geometry,
   - width by road class,
   - elevation sampled from terrain,
   - z-smoothed to reduce unrealistic grade spikes.
7. Generate junction pads where road nodes have degree 3+.
8. Generate simple building massing.
9. Save Blender file and audit report.

## Road Standards Heuristics

This first pass is not a civil engineering solver. It applies conservative game-environment heuristics:

- Road widths by OSM class:
  - primary/trunk: 10-12 m
  - secondary/tertiary: 8-9 m
  - residential/unclassified: 5-6 m
  - service/track/path/footway/cycleway: 2-4 m
- Junctions get visible pads to avoid visually broken centerline overlaps.
- Road z values are smoothed when terrain samples create peaky slopes.
- Sharp bends are preserved geometrically but flagged in the report when segment angles are extreme.

## Future Upgrade Path

- Replace polyline curves with Bezier splines with handle generation.
- Build real roadbed mesh ribbons from curve frame normals.
- Cut or shrinkwrap roads into terrain.
- Add lane markings, curbs, shoulders, and guardrails with Geometry Nodes.
- Use terrain tiles or local DEM rasters for higher resolution than public point sampling.
- Add graph-level road rules:
  - turn radii,
  - intersection hierarchy,
  - grade limits by road class,
  - bridge/tunnel handling,
  - drainage/camber.

