from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    args = sys.argv
    if "--" in args:
        args = args[args.index("--") + 1 :]
    else:
        args = []
    parser = argparse.ArgumentParser(description="Render an oblique continuity preview for a corridor proof blend.")
    parser.add_argument("--output", required=True, help="Render output prefix.")
    parser.add_argument("--resolution-x", type=int, default=1800)
    parser.add_argument("--resolution-y", type=int, default=1100)
    return parser.parse_args(args)


def world_bbox(objects: Iterable[bpy.types.Object]) -> Tuple[Vector, Vector]:
    mins = Vector((math.inf, math.inf, math.inf))
    maxs = Vector((-math.inf, -math.inf, -math.inf))
    found = False
    for obj in objects:
        if not obj.bound_box:
            continue
        found = True
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            mins.x = min(mins.x, world.x)
            mins.y = min(mins.y, world.y)
            mins.z = min(mins.z, world.z)
            maxs.x = max(maxs.x, world.x)
            maxs.y = max(maxs.y, world.y)
            maxs.z = max(maxs.z, world.z)
    if not found:
        raise RuntimeError("No renderable focus objects found")
    return mins, maxs


def focus_objects() -> List[bpy.types.Object]:
    prefixes = (
        "ab_flattened_terrain",
        "flattened_centerline",
        "roadbed_flattened",
        "junction_pad",
        "junction_connector",
    )
    return [obj for obj in bpy.context.scene.objects if obj.name.startswith(prefixes)]


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    args = parse_args()
    focus = focus_objects()
    mins, maxs = world_bbox(focus)
    center = (mins + maxs) / 2.0
    span = max(maxs.x - mins.x, maxs.y - mins.y, 80.0)
    height = max(maxs.z - mins.z, 28.0)

    bpy.ops.object.light_add(type="AREA", location=(center.x - 80.0, center.y - 160.0, center.z + 160.0))
    light = bpy.context.object
    light.name = "oblique_area_key"
    light.data.energy = 450.0
    light.data.size = 150.0

    bpy.ops.object.camera_add(location=(center.x - span * 0.18, center.y - span * 0.86, center.z + height * 3.7))
    camera = bpy.context.object
    camera.name = "oblique_continuity_camera"
    look_at(camera, Vector((center.x, center.y, center.z + height * 0.45)))
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = span * 1.05
    bpy.context.scene.camera = camera

    bpy.context.scene.render.resolution_x = args.resolution_x
    bpy.context.scene.render.resolution_y = args.resolution_y
    bpy.context.scene.eevee.taa_render_samples = 48
    bpy.context.scene.render.filepath = str(Path(args.output).resolve())
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
