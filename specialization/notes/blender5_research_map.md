# Blender 5.x Research Map

## What Matters for This Specialization

Blender 5.x is relevant here for four reasons:

1. Python automation remains the control spine for reproducible terrain/road generation.
2. Curves can represent road centerlines with bevels, tapering, and 3D path control.
3. Geometry Nodes is the natural future layer for non-destructive road shoulders, lane markings, guardrails, vegetation scattering, and terrain blending.
4. EEVEE/viewport curve improvements matter for inspecting dense road splines without converting everything to mesh too early.

## Working Capability Targets

- Create and edit 3D curves from code.
- Attach road metadata to generated objects.
- Convert curves or sampled centerlines into mesh strips when needed.
- Build terrain meshes from sampled DEM grids.
- Place building massing from footprints and level/height tags.
- Store audit data beside every Blender artifact.

## Current Local Tooling

- Blender executable: `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
- Version observed: Blender 5.1.2, release build dated 2026-05-19.
- Python geospatial stack in the repo venv is minimal. First proof uses stdlib + `requests` + Blender `bpy`.

## Open Questions

- Which Blender add-ons should become optional acceleration layers versus hard dependencies?
- How much road correctness should be handled before Blender versus inside Geometry Nodes?
- Should terrain blending become mesh deformation, shader masking, or a generated roadbed mesh?
- What is the minimum game-ready export path: `.blend`, `.fbx`, `.glb`, or Unreal/Unity-specific packaging?

