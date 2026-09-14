# Blender MCP / Skill Brief

This repo does not currently have a dedicated Blender MCP server wired into ParaLLM. The first specialization pass therefore treats Blender as a headless executable controlled by Python scripts.

## Desired Skill Surface

An eventual Blender skill or MCP lane should expose:

- `inspect_scene`: list objects, materials, collections, file metadata.
- `run_blender_python`: execute bounded scripts with captured stdout/stderr.
- `create_curve_network`: create road/river/path curves from structured point data.
- `create_terrain_mesh`: build terrain from DEM grid input.
- `sample_surface_height`: query terrain z for a point.
- `export_scene`: save `.blend`, `.fbx`, `.glb`, and report metadata.
- `render_preview`: produce a viewport or camera render for review.

## Safety Requirements

- Scripts run in a controlled project folder.
- No arbitrary filesystem writes outside approved output roots.
- Every generated artifact has a report file.
- Any add-on install is explicit and recorded.
- Long-running Blender jobs write periodic progress markers.

## Immediate Local Equivalent

Use:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python specialization/scripts/blender_generate_terrain_roads.py
```

