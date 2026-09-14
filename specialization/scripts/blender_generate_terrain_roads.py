from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import bpy


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "Specialization" / "output" / "data" / "terrain_roads_dataset.json"
BLENDER_OUT = ROOT / "Specialization" / "output" / "blender"
REPORT_OUT = ROOT / "Specialization" / "output" / "reports"


def load_dataset() -> Dict[str, Any]:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def material(name: str, color: Tuple[float, float, float, float], emission: float = 0.0) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.85
        if emission and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = color
        if emission and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission
    return mat


def elevation_min(data: Dict[str, Any]) -> float:
    return min(min(row) for row in data["elevation"]["grid"])


def normalized_z(z: float, z_min: float, lift: float = 0.0) -> float:
    return (z - z_min) * 0.75 + lift


def terrain_mesh(data: Dict[str, Any], mat: bpy.types.Material) -> bpy.types.Object:
    elev = data["elevation"]
    lats = elev["lats"]
    lons = elev["lons"]
    grid = elev["grid"]
    lat0 = data["projection"]["lat0"]
    lon0 = data["projection"]["lon0"]
    z_min = elevation_min(data)
    verts = []
    faces = []
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            x, y = project(lat, lon, lat0, lon0)
            z = normalized_z(grid[i][j], z_min)
            verts.append((x, y, z))
    samples = len(lats)
    for i in range(samples - 1):
        for j in range(samples - 1):
            a = i * samples + j
            faces.append((a, a + 1, a + samples + 1, a + samples))
    mesh = bpy.data.meshes.new("terrain_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("terrain_dem_mesh", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def project(lat: float, lon: float, lat0: float, lon0: float) -> Tuple[float, float]:
    meters_per_deg_lat = 110_574.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    return (lon - lon0) * meters_per_deg_lon, (lat - lat0) * meters_per_deg_lat


def smooth_z(points: List[Dict[str, float]], z_min: float, passes: int = 2) -> List[Tuple[float, float, float]]:
    coords = [(p["x"], p["y"], p["z"]) for p in points]
    if len(coords) < 3:
        return coords
    for _ in range(passes):
        next_coords = [coords[0]]
        for i in range(1, len(coords) - 1):
            x, y, z = coords[i]
            z_avg = (coords[i - 1][2] + z * 2.0 + coords[i + 1][2]) / 4.0
            next_coords.append((x, y, z_avg))
        next_coords.append(coords[-1])
        coords = next_coords
    return [(x, y, normalized_z(z, z_min, 0.85)) for x, y, z in coords]


def create_road_curve(road: Dict[str, Any], mat: bpy.types.Material, z_min: float) -> bpy.types.Object | None:
    coords = smooth_z(road["points"], z_min)
    if len(coords) < 2:
        return None
    curve = bpy.data.curves.new(f"road_{road['id']}_{road['highway']}", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 12
    curve.bevel_depth = max(float(road.get("width_m") or 4.0) * 0.08, 0.22)
    curve.bevel_resolution = 1
    curve.twist_smooth = 6
    spline = curve.splines.new("POLY")
    spline.points.add(len(coords) - 1)
    for point, (x, y, z) in zip(spline.points, coords):
        point.co = (x, y, z, 1.0)
    obj = bpy.data.objects.new(curve.name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    obj["osm_id"] = str(road.get("id"))
    obj["highway"] = str(road.get("highway"))
    obj["source"] = "OpenStreetMap Overpass"
    return obj


def create_junction_pad(point: Dict[str, Any], mat: bpy.types.Material, index: int, z_min: float) -> bpy.types.Object:
    z = normalized_z(float(point.get("z") or z_min), z_min, 1.0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=4.0 + min(7.0, float(point.get("degree") or 3)), depth=0.18, location=(point["x"], point["y"], z))
    obj = bpy.context.object
    obj.name = f"junction_pad_{index:03d}_degree_{point.get('degree', 0)}"
    obj.data.materials.append(mat)
    return obj


def create_building(building: Dict[str, Any], mat: bpy.types.Material, index: int, z_min: float) -> bpy.types.Object | None:
    footprint = building.get("footprint") or []
    if len(footprint) < 3:
        return None
    base_z = sum(normalized_z(float(p.get("z") or z_min), z_min, 0.25) for p in footprint) / len(footprint)
    base = [(p["x"], p["y"], base_z) for p in footprint]
    if distance2(base[0], base[-1]) < 0.5:
        base = base[:-1]
    if len(base) < 3:
        return None
    height = float(building.get("height_m") or 6.5)
    top = [(x, y, z + height) for x, y, z in base]
    verts = base + top
    n = len(base)
    faces = [tuple(range(n)), tuple(range(n, n * 2))]
    for i in range(n):
        faces.append((i, (i + 1) % n, (i + 1) % n + n, i + n))
    mesh = bpy.data.meshes.new(f"building_{building.get('id', index)}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f"building_{index:03d}_{building.get('id', '')}", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    obj["osm_id"] = str(building.get("id"))
    obj["building"] = str(building.get("building"))
    obj["height_m"] = height
    return obj


def distance2(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def scene_bounds(data: Dict[str, Any]) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    for road in data.get("roads", []):
        for point in road.get("points", []):
            xs.append(float(point["x"]))
            ys.append(float(point["y"]))
    for building in data.get("buildings", []):
        for point in building.get("footprint", []):
            xs.append(float(point["x"]))
            ys.append(float(point["y"]))
    if not xs or not ys:
        return -100.0, -100.0, 100.0, 100.0
    return min(xs), min(ys), max(xs), max(ys)


def add_labels(data: Dict[str, Any], z_min: float) -> None:
    area = data["area"]
    min_x, min_y, max_x, max_y = scene_bounds(data)
    bpy.ops.object.text_add(location=(min_x + 18, max_y - 28, normalized_z(z_min, z_min, 25)), rotation=(0, 0, 0))
    label = bpy.context.object
    label.name = "scene_label"
    label.data.body = f"{area['name']}, {area['country']} - terrain + OSM roads"
    label.data.align_x = "LEFT"
    label.data.size = 5.0


def setup_camera(data: Dict[str, Any]) -> None:
    min_x, min_y, max_x, max_y = scene_bounds(data)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    span = max(max_x - min_x, max_y - min_y)
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 120))
    sun = bpy.context.object
    sun.name = "sun_key"
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(35), 0, math.radians(35))
    bpy.ops.object.camera_add(location=(center_x, center_y, 900), rotation=(0, 0, 0))
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = span * 1.08
    bpy.context.scene.camera = camera
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.eevee.taa_render_samples = 32
    bpy.context.scene.world.color = (0.02, 0.035, 0.045)


def write_report(data: Dict[str, Any], road_count: int, building_count: int, junction_count: int) -> None:
    REPORT_OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "area": data["area"],
        "bbox": data["bbox"],
        "sources": data["sources"],
        "generated": {
            "terrainMesh": True,
            "roadCurveCount": road_count,
            "buildingMassingCount": building_count,
            "junctionPadCount": junction_count,
        },
        "limitations": [
            "Roads are curve centerlines with bevel depth, not yet terrain-cut roadbed ribbons.",
            "Junctions are heuristic pads based on endpoint degree; mid-way intersections need graph splitting.",
            "Elevation is sampled from 90 m DEM, too coarse for final high-detail game terrain.",
            "Buildings are simple massing extrusions from OSM footprints and tags.",
        ],
    }
    (REPORT_OUT / "blender_generation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    BLENDER_OUT.mkdir(parents=True, exist_ok=True)
    data = load_dataset()
    reset_scene()
    z_min = elevation_min(data)
    terrain_mat = material("terrain_matte_green", (0.12, 0.25, 0.16, 1.0))
    road_mat = material("road_cyan_trace", (0.08, 0.75, 0.95, 1.0), emission=0.35)
    junction_mat = material("junction_blueprint_pad", (0.05, 0.40, 0.95, 1.0), emission=0.45)
    building_mat = material("building_soft_concrete", (0.58, 0.54, 0.48, 1.0))
    terrain_mesh(data, terrain_mat)
    road_count = 0
    for road in data.get("roads", []):
        if create_road_curve(road, road_mat, z_min):
            road_count += 1
    junction_count = 0
    for index, junction in enumerate(data.get("junctions", [])[:120], start=1):
        create_junction_pad(junction, junction_mat, index, z_min)
        junction_count += 1
    building_count = 0
    for index, building in enumerate(data.get("buildings", [])[:300], start=1):
        if create_building(building, building_mat, index, z_min):
            building_count += 1
    add_labels(data, z_min)
    setup_camera(data)
    write_report(data, road_count, building_count, junction_count)
    blend_path = BLENDER_OUT / "terrain_road_network_proof.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(json.dumps({
        "blend": str(blend_path),
        "roads": road_count,
        "buildings": building_count,
        "junctions": junction_count,
    }, indent=2))


if __name__ == "__main__":
    main()
