# Kotor Corridor A/B Plan

## Goal

Use the existing Kotor OSM/elevation dataset to create a focused Blender proof comparing:

- A: current road-as-curve baseline,
- B: terrain-conforming roadbed ribbon mesh.

## Why This Is Next

The first proof established ingest and Blender generation, but Para and Codex both found the next uncertainty:

- roads are still centerline curves,
- junctions are heuristic endpoint pads,
- terrain preview has visible elevation/render banding,
- the dataset is steep enough to expose road/terrain errors.

## Steps

1. Analyze `specialization/output/data/terrain_roads_dataset.json`.
2. Pick a corridor with enough length, grade, and point density to inspect.
3. Generate one Blender A/B scene:
   - left side: baseline curve road on terrain,
   - right side: roadbed ribbon mesh on the same terrain,
   - include local building context and junction markers where relevant,
   - add labels and camera framing.
4. Render a preview image.
5. Ask Para to pressure-review only the compact report and preview context.
6. Record what improved, what failed, and the next concrete test.

## Success Criteria

- A `.blend` exists for the corridor A/B proof.
- A preview PNG exists and shows both baseline and roadbed variant.
- A JSON report records the selected road, length, grade, width, source ids, and limitations.
- The report states whether the next blocker is roadbed geometry, terrain source quality, or junction splitting.

