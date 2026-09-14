# Para Commander Packet - Blender/GIS Specialization

- Task: `t-20260602-041100-571df1`
- Round: `1`
- Stance: `caution`

## Lead Direction

Build a source-first packet around native Blender curve/NURBS road and terrain generation, with BlenderGIS optional and all Blender 5.x specifics held to verification.

## Answer Draft

[fact] Blender's curve stack already covers Bezier/NURBS, bevel/extrude/taper, and curve-to-mesh; the Python API exposes curve operators such as `bpy.ops.curve.primitive_bezier_curve_add` and `bpy.ops.curve.primitive_nurbs_curve_add`, plus geometry properties for bevel, taper, and 2D/3D behavior, and Geometry Nodes like Curve to Mesh, Resample Curve, Set Curve Radius, and Set Curve Tilt. [fact] BlenderGIS README documents minimum Blender v2.83 plus OSM XML, GeoTIFF DEM, shapefile, and web OSM/elevation import, and it can compute terrain meshes by Delaunay triangulation. [fact] OSM `highway=*`, `route=road`, and `relation:connectivity` are relevant to road graphs and lane stitching; if lane-level fidelity is missing, stay centerline-first and infer only minimal transitions. [assumption] Provisional pipeline: OSM+DEM ingest -> CRS/unit normalization with PROJ/GDAL -> centerline cleanup and grade/bend smoothing -> road curves/meshes with width, tilt, taper, and junction widening -> terrain drape -> bake/export to glTF/FBX. Source anchors: https://docs.blender.org/manual/en/latest/modeling/curves/index.html ; https://docs.blender.org/manual/en/latest/modeling/curves/properties/geometry.html ; https://docs.blender.org/api/current/bpy.ops.curve.html ; https://docs.blender.org/api/current/bpy.types.Curve.html ; https://docs.blender.org/manual/en/dev/addons/import_export/scene_gltf2...

## Why This Direction

This is the best first pass because it turns a broad research request into a concrete, source-anchored workflow without pretending the 5.x build has been validated. The main risks are API drift, add-on brittleness, and CRS/export mistakes, so those should be explicit checks rather than hidden assumptions.

## Pressure Points

- [unknown] Exact 5.x API names and node labels may have drifted from the current docs.
- [unknown] BlenderGIS README proves features and minimum version, but not Blender 5.x compatibility.
- [unknown] OSM road data often omits lane widths, grades, and surface detail, so road math will be heuristic unless a target road class is specified.
- [fact] CRS/unit normalization must be explicit or terrain alignment can break silently.

## Questions For Workers

- Which exact current Blender 5.x docs prove the curve, bevel/taper, and curve-node claims we want to cite, and what changed from the current manual/API pages?
- What is the strongest reason not to state numeric road grade, bend radius, or junction rules until a road class and target engine are chosen?
- Can the OSM/DEM import path stay viable without BlenderGIS, and if not, what fallback remains when that add-on is stale or unavailable?

## Keep Course If

- [fact] Official docs confirm the same native curve/GN path with only small naming or UI differences.
- [fact] BlenderGIS remains usable as optional import help rather than a hard dependency.
- [assumption] Road math can stay heuristic because the target is game-ready terrain, not civil-engineering-grade roadway design.

## Change Course If

- [unknown] Official 5.x docs or a minimal test show the native curve/GN workflow is not viable.
- [unknown] BlenderGIS or the GIS ingest path is too stale or incompatible to mention even as an optional helper.
- [inference] The scope shifts to civil-engineering-accurate roadway design, which would require a different abstraction and source set.

## Uncertainty

- [unknown] No Blender test artifact was inspected in this round, so runtime behavior remains unverified.
- [unknown] The exact 5.x API/nodes available in the installed build may differ slightly from current docs.
- [assumption] Road grade, bend, and junction thresholds need a target road class and engine budget before they can be tightened.
