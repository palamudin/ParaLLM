from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

import bpy


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "specialization" / "output" / "data" / "terrain_roads_dataset.json"
OUT = ROOT / "specialization" / "output"
BLENDER_OUT = OUT / "blender"
REPORT_OUT = OUT / "reports"

ROAD_CLASSES = {"residential", "service", "unclassified", "living_street", "tertiary", "secondary", "primary"}


def parse_args() -> argparse.Namespace:
    args = sys.argv
    if "--" in args:
        args = args[args.index("--") + 1 :]
    else:
        args = []
    parser = argparse.ArgumentParser(description="Generate a corridor A/B/C Blender proof.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Path to normalized terrain/roads JSON dataset.")
    parser.add_argument("--output-prefix", default="kotor_corridor_abc", help="Output filename prefix for blend/report/render.")
    return parser.parse_args(args)


def load_dataset(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
            bsdf.inputs["Roughness"].default_value = 0.82
        if emission and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = color
        if emission and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission
    return mat


def z_min(data: Dict[str, Any]) -> float:
    return min(min(row) for row in data["elevation"]["grid"])


def norm_z(value: float, floor: float, lift: float = 0.0) -> float:
    return (value - floor) * 0.75 + lift


def project(lat: float, lon: float, lat0: float, lon0: float) -> Tuple[float, float]:
    meters_per_deg_lat = 110_574.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    return (lon - lon0) * meters_per_deg_lon, (lat - lat0) * meters_per_deg_lat


def unproject(x: float, y: float, lat0: float, lon0: float) -> Tuple[float, float]:
    meters_per_deg_lat = 110_574.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    lat = y / meters_per_deg_lat + lat0
    lon = x / meters_per_deg_lon + lon0
    return lat, lon


def road_metrics(road: Dict[str, Any]) -> Dict[str, float]:
    points = road.get("points") or []
    length = 0.0
    for a, b in zip(points, points[1:]):
        length += math.hypot(float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"]))
    relief = max(float(p["z"]) for p in points) - min(float(p["z"]) for p in points) if points else 0.0
    grade = relief / length if length else 0.0
    return {"length_m": length, "relief_m": relief, "grade": grade}


def road_profile_summary(road: Dict[str, Any]) -> Dict[str, Any]:
    points = road.get("points") or []
    segment_grades = []
    segment_lengths = []
    for a, b in zip(points, points[1:]):
        length = math.hypot(float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"]))
        dz = float(b["z"]) - float(a["z"])
        if length:
            segment_lengths.append(length)
            segment_grades.append(abs(dz) / length)
    z_values = [float(point["z"]) for point in points]
    return {
        "segmentCount": max(len(points) - 1, 0),
        "minSegmentLengthM": round(min(segment_lengths), 3) if segment_lengths else 0.0,
        "maxSegmentLengthM": round(max(segment_lengths), 3) if segment_lengths else 0.0,
        "maxAbsSegmentGrade": round(max(segment_grades), 4) if segment_grades else 0.0,
        "meanAbsSegmentGrade": round(sum(segment_grades) / len(segment_grades), 4) if segment_grades else 0.0,
        "minElevationM": round(min(z_values), 3) if z_values else 0.0,
        "maxElevationM": round(max(z_values), 3) if z_values else 0.0,
    }


def select_corridor(data: Dict[str, Any]) -> Dict[str, Any]:
    candidates = []
    for road in data.get("roads", []):
        points = road.get("points") or []
        if len(points) < 6:
            continue
        if str(road.get("highway") or "") not in ROAD_CLASSES:
            continue
        metrics = road_metrics(road)
        if metrics["length_m"] < 60:
            continue
        score = metrics["grade"] * 100.0 + min(metrics["length_m"] / 100.0, 3.0) + min(len(points) / 8.0, 2.0)
        candidates.append((score, road, metrics))
    if not candidates:
        raise RuntimeError("No suitable road-class corridor found in dataset")
    _score, road, metrics = max(candidates, key=lambda item: item[0])
    road["corridorMetrics"] = metrics
    return road


def bounds_for_points(points: Iterable[Dict[str, float]], padding: float = 85.0) -> Tuple[float, float, float, float]:
    pts = list(points)
    min_x = min(float(p["x"]) for p in pts) - padding
    max_x = max(float(p["x"]) for p in pts) + padding
    min_y = min(float(p["y"]) for p in pts) - padding
    max_y = max(float(p["y"]) for p in pts) + padding
    return min_x, min_y, max_x, max_y


def in_bounds_xy(point: Dict[str, float], bounds: Tuple[float, float, float, float]) -> bool:
    min_x, min_y, max_x, max_y = bounds
    return min_x <= float(point["x"]) <= max_x and min_y <= float(point["y"]) <= max_y


def cumulative_stations(points: List[Dict[str, float]]) -> List[float]:
    stations = [0.0]
    for a, b in zip(points, points[1:]):
        stations.append(stations[-1] + math.hypot(float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"])))
    return stations


def interpolate_point(a: Dict[str, float], b: Dict[str, float], t: float) -> Dict[str, float]:
    return {
        "x": float(a["x"]) + (float(b["x"]) - float(a["x"])) * t,
        "y": float(a["y"]) + (float(b["y"]) - float(a["y"])) * t,
        "z": float(a["z"]) + (float(b["z"]) - float(a["z"])) * t,
    }


def nearest_corridor_sample(x: float, y: float, points: List[Dict[str, float]]) -> Dict[str, float]:
    stations = cumulative_stations(points)
    best: Optional[Dict[str, float]] = None
    for index, (a, b) in enumerate(zip(points, points[1:])):
        ax, ay = float(a["x"]), float(a["y"])
        bx, by = float(b["x"]), float(b["y"])
        dx = bx - ax
        dy = by - ay
        denom = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / denom)) if denom else 0.0
        sample = interpolate_point(a, b, t)
        distance = math.hypot(x - sample["x"], y - sample["y"])
        station = stations[index] + math.hypot(sample["x"] - ax, sample["y"] - ay)
        candidate = {
            "x": sample["x"],
            "y": sample["y"],
            "z": sample["z"],
            "distance": distance,
            "station": station,
            "segmentIndex": float(index),
            "segmentT": t,
        }
        if best is None or distance < best["distance"]:
            best = candidate
    if best is None:
        raise ValueError("Corridor must have at least two points")
    return best


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge1 <= edge0:
        return 1.0
    t = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def flattened_raw_elevation(x: float, y: float, raw_z: float, profile: Dict[str, Any]) -> float:
    sample = nearest_corridor_sample(x, y, profile["points"])
    half_width = float(profile.get("halfWidthM", 4.0))
    blend_width = float(profile.get("blendWidthM", 7.0))
    cut_depth = float(profile.get("cutDepthM", 0.18))
    target_z = float(sample["z"]) - cut_depth
    distance = float(sample["distance"])
    if distance <= half_width:
        return target_z
    if distance <= half_width + blend_width:
        weight = 1.0 - smoothstep(half_width, half_width + blend_width, distance)
        raw_z = raw_z * (1.0 - weight) + target_z * weight
    for junction in profile.get("junctions", []):
        junction_radius = float(profile.get("junctionRadiusM", 7.0))
        junction_blend = float(profile.get("junctionBlendM", 5.0))
        junction_distance = math.hypot(x - float(junction["x"]), y - float(junction["y"]))
        junction_target = float(junction["z"]) - cut_depth
        if junction_distance <= junction_radius:
            raw_z = junction_target
        elif junction_distance <= junction_radius + junction_blend:
            weight = 1.0 - smoothstep(junction_radius, junction_radius + junction_blend, junction_distance)
            raw_z = raw_z * (1.0 - weight) + junction_target * weight
    return raw_z


def segment_intersection(
    a: Dict[str, float],
    b: Dict[str, float],
    c: Dict[str, float],
    d: Dict[str, float],
) -> Optional[Tuple[float, float, float, float]]:
    ax, ay = float(a["x"]), float(a["y"])
    bx, by = float(b["x"]), float(b["y"])
    cx, cy = float(c["x"]), float(c["y"])
    dx, dy = float(d["x"]), float(d["y"])
    rx, ry = bx - ax, by - ay
    sx, sy = dx - cx, dy - cy
    denom = rx * sy - ry * sx
    if abs(denom) < 1e-9:
        return None
    qx, qy = cx - ax, cy - ay
    t = (qx * sy - qy * sx) / denom
    u = (qx * ry - qy * rx) / denom
    if 0.02 < t < 0.98 and 0.02 < u < 0.98:
        return t, u, ax + t * rx, ay + t * ry
    return None


def find_corridor_junctions(data: Dict[str, Any], corridor: Dict[str, Any], tolerance_m: float = 8.0) -> List[Dict[str, Any]]:
    points = corridor.get("points") or []
    stations = cumulative_stations(points)
    grouped: Dict[float, Dict[str, Any]] = {}

    def add_junction(
        *,
        kind: str,
        station: float,
        x: float,
        y: float,
        z: float,
        segment_index: int,
        segment_t: float,
        distance: float,
        road: Dict[str, Any],
        endpoint: str = "",
    ) -> None:
        key = round(station, 1)
        existing = grouped.get(key)
        connection = {
            "roadId": road.get("id"),
            "highway": road.get("highway") or "",
            "kind": kind,
            "distanceM": round(distance, 3),
            "endpoint": endpoint,
        }
        if existing:
            existing["connections"].append(connection)
            existing["kinds"] = sorted(set(existing["kinds"] + [kind]))
            existing["distanceM"] = min(existing["distanceM"], round(distance, 3))
            return
        grouped[key] = {
            "stationM": round(station, 3),
            "x": x,
            "y": y,
            "z": z,
            "segmentIndex": segment_index,
            "segmentT": round(segment_t, 4),
            "distanceM": round(distance, 3),
            "kinds": [kind],
            "connections": [connection],
        }

    for segment_index, (a, b) in enumerate(zip(points, points[1:])):
        seg_len = math.hypot(float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"]))
        for road in data.get("roads", []):
            if road.get("id") == corridor.get("id"):
                continue
            other_points = road.get("points") or []
            for c, d in zip(other_points, other_points[1:]):
                hit = segment_intersection(a, b, c, d)
                if hit is None:
                    continue
                t, _u, x, y = hit
                sample = interpolate_point(a, b, t)
                add_junction(
                    kind="crossing",
                    station=stations[segment_index] + seg_len * t,
                    x=x,
                    y=y,
                    z=sample["z"],
                    segment_index=segment_index,
                    segment_t=t,
                    distance=0.0,
                    road=road,
                )

    for road in data.get("roads", []):
        if road.get("id") == corridor.get("id"):
            continue
        other_points = road.get("points") or []
        if not other_points:
            continue
        endpoint_pairs = (("start", other_points[0]), ("end", other_points[-1]))
        for endpoint_label, endpoint_point in endpoint_pairs:
            sample = nearest_corridor_sample(float(endpoint_point["x"]), float(endpoint_point["y"]), points)
            if sample["distance"] <= tolerance_m:
                add_junction(
                    kind="near_endpoint",
                    station=sample["station"],
                    x=sample["x"],
                    y=sample["y"],
                    z=sample["z"],
                    segment_index=int(sample["segmentIndex"]),
                    segment_t=float(sample["segmentT"]),
                    distance=float(sample["distance"]),
                    road=road,
                    endpoint=endpoint_label,
                )
    return sorted(grouped.values(), key=lambda item: float(item["stationM"]))


def split_corridor_by_junctions(corridor: Dict[str, Any], junctions: List[Dict[str, Any]]) -> Dict[str, Any]:
    split_corridor = copy.deepcopy(corridor)
    points = split_corridor.get("points") or []
    stations = cumulative_stations(points)
    enriched = []
    for station, point in zip(stations, points):
        item = dict(point)
        item["stationM"] = station
        enriched.append(item)
    existing_stations = [float(point["stationM"]) for point in enriched]
    for junction in junctions:
        station = float(junction["stationM"])
        if any(abs(station - existing) < 0.75 for existing in existing_stations):
            continue
        enriched.append(
            {
                "x": float(junction["x"]),
                "y": float(junction["y"]),
                "z": float(junction["z"]),
                "stationM": station,
                "generatedSplit": True,
            }
        )
        existing_stations.append(station)
    enriched.sort(key=lambda point: float(point["stationM"]))
    split_corridor["points"] = enriched
    split_corridor["splitStationsM"] = sorted({round(float(junction["stationM"]), 3) for junction in junctions})
    return split_corridor


def bilinear_elevation(lat: float, lon: float, elev: Dict[str, Any]) -> float:
    lats = elev["lats"]
    lons = elev["lons"]
    grid = elev["grid"]
    lat = max(min(lat, lats[-1]), lats[0])
    lon = max(min(lon, lons[-1]), lons[0])
    lat_step = (lats[-1] - lats[0]) / (len(lats) - 1)
    lon_step = (lons[-1] - lons[0]) / (len(lons) - 1)
    fi = (lat - lats[0]) / lat_step if lat_step else 0.0
    fj = (lon - lons[0]) / lon_step if lon_step else 0.0
    i = min(max(int(math.floor(fi)), 0), len(lats) - 2)
    j = min(max(int(math.floor(fj)), 0), len(lons) - 2)
    di = fi - i
    dj = fj - j
    z00 = grid[i][j]
    z10 = grid[i + 1][j]
    z01 = grid[i][j + 1]
    z11 = grid[i + 1][j + 1]
    return (z00 * (1 - di) * (1 - dj)) + (z10 * di * (1 - dj)) + (z01 * (1 - di) * dj) + (z11 * di * dj)


def make_terrain_panel(
    data: Dict[str, Any],
    bounds: Tuple[float, float, float, float],
    x_shift: float,
    mat: bpy.types.Material,
    name: str,
    flatten_profile: Optional[Dict[str, Any]] = None,
) -> bpy.types.Object:
    elev = data["elevation"]
    floor = z_min(data)
    lat0 = data["projection"]["lat0"]
    lon0 = data["projection"]["lon0"]
    verts: List[Tuple[float, float, float]] = []
    samples = 34
    min_x, min_y, max_x, max_y = bounds
    for i in range(samples):
        y = min_y + (max_y - min_y) * i / (samples - 1)
        for j in range(samples):
            x = min_x + (max_x - min_x) * j / (samples - 1)
            lat, lon = unproject(x, y, lat0, lon0)
            raw_z = bilinear_elevation(lat, lon, elev)
            if flatten_profile is not None:
                raw_z = flattened_raw_elevation(x, y, raw_z, flatten_profile)
            verts.append((x + x_shift, y, norm_z(raw_z, floor)))
    faces = []
    for i in range(samples - 1):
        for j in range(samples - 1):
            a = i * samples + j
            faces.append((a, a + 1, a + samples + 1, a + samples))
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def smooth_coords(points: List[Dict[str, float]], floor: float, passes: int = 2) -> List[Tuple[float, float, float]]:
    coords = [(float(p["x"]), float(p["y"]), float(p["z"])) for p in points]
    for _ in range(passes):
        if len(coords) < 3:
            break
        nxt = [coords[0]]
        for i in range(1, len(coords) - 1):
            x, y, z = coords[i]
            z_avg = (coords[i - 1][2] + z * 2.0 + coords[i + 1][2]) / 4.0
            nxt.append((x, y, z_avg))
        nxt.append(coords[-1])
        coords = nxt
    return [(x, y, norm_z(z, floor, 1.2)) for x, y, z in coords]


def make_curve_road(
    road: Dict[str, Any],
    x_shift: float,
    mat: bpy.types.Material,
    floor: float,
    name_prefix: str,
    width_scale: float = 0.08,
) -> bpy.types.Object:
    coords = smooth_coords(road["points"], floor)
    curve = bpy.data.curves.new(f"{name_prefix}_{road['id']}", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 12
    curve.bevel_depth = max(float(road.get("width_m") or 4.0) * width_scale, 0.18)
    curve.bevel_resolution = 1
    spline = curve.splines.new("POLY")
    spline.points.add(len(coords) - 1)
    for point, (x, y, z) in zip(spline.points, coords):
        point.co = (x + x_shift, y, z, 1.0)
    obj = bpy.data.objects.new(curve.name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def make_roadbed_mesh(
    road: Dict[str, Any],
    x_shift: float,
    mat: bpy.types.Material,
    floor: float,
    name_prefix: str = "roadbed",
) -> bpy.types.Object:
    coords = smooth_coords(road["points"], floor, passes=3)
    half_width = max(float(road.get("width_m") or 4.0) / 2.0, 2.0)
    shoulder = 1.2
    verts: List[Tuple[float, float, float]] = []
    for idx, (x, y, z) in enumerate(coords):
        prev_pt = coords[max(idx - 1, 0)]
        next_pt = coords[min(idx + 1, len(coords) - 1)]
        dx = next_pt[0] - prev_pt[0]
        dy = next_pt[1] - prev_pt[1]
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        for side in (-1.0, 1.0):
            width = half_width + shoulder
            verts.append((x + x_shift + nx * width * side, y + ny * width * side, z + 0.18))
    faces = []
    for i in range(len(coords) - 1):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    mesh = bpy.data.meshes.new(f"{name_prefix}_{road['id']}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f"{name_prefix}_{road['id']}_terrain_ribbon", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def make_junction_markers(
    junctions: List[Dict[str, Any]],
    x_shift: float,
    mat: bpy.types.Material,
    floor: float,
) -> None:
    for index, junction in enumerate(junctions, start=1):
        radius = 3.2 if "crossing" in junction.get("kinds", []) else 2.5
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=28,
            radius=radius,
            depth=0.55,
            location=(float(junction["x"]) + x_shift, float(junction["y"]), norm_z(float(junction["z"]), floor, 1.75)),
        )
        obj = bpy.context.object
        obj.name = f"junction_split_marker_{index:02d}"
        obj.data.materials.append(mat)


def make_junction_pad_mesh(
    junction: Dict[str, Any],
    x_shift: float,
    mat: bpy.types.Material,
    floor: float,
    index: int,
    radius: float = 7.0,
) -> bpy.types.Object:
    z = norm_z(float(junction["z"]), floor, 1.68)
    verts = [(float(junction["x"]) + x_shift, float(junction["y"]), z)]
    faces = []
    segments = 36
    for i in range(segments):
        angle = math.tau * i / segments
        verts.append((float(junction["x"]) + x_shift + math.cos(angle) * radius, float(junction["y"]) + math.sin(angle) * radius, z))
    for i in range(1, segments + 1):
        faces.append((0, i, 1 if i == segments else i + 1))
    mesh = bpy.data.meshes.new(f"junction_pad_{index:02d}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f"junction_pad_{index:02d}", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def connector_stub_points(
    junction: Dict[str, Any],
    road: Dict[str, Any],
    endpoint: str,
    max_points: int = 4,
) -> List[Dict[str, float]]:
    road_points = road.get("points") or []
    if len(road_points) < 2:
        return []
    if endpoint == "end":
        chosen = list(reversed(road_points[-max_points:]))
    else:
        chosen = list(road_points[:max_points])
    junction_point = {
        "x": float(junction["x"]),
        "y": float(junction["y"]),
        "z": float(junction["z"]),
    }
    if math.hypot(float(chosen[0]["x"]) - junction_point["x"], float(chosen[0]["y"]) - junction_point["y"]) < 0.75:
        return [junction_point] + [dict(point) for point in chosen[1:]]
    return [junction_point] + [dict(point) for point in chosen]


def make_junction_geometry(
    junctions: List[Dict[str, Any]],
    roads_by_id: Dict[Any, Dict[str, Any]],
    x_shift: float,
    mat: bpy.types.Material,
    floor: float,
) -> Dict[str, Any]:
    pad_radius = 7.0
    pads = 0
    stubs = 0
    checks = []
    for index, junction in enumerate(junctions, start=1):
        make_junction_pad_mesh(junction, x_shift, mat, floor, index, radius=pad_radius)
        pads += 1
        junction_check = {
            "stationM": float(junction["stationM"]),
            "padRadiusM": pad_radius,
            "corridorPassesThroughPad": True,
            "connectors": [],
        }
        for conn_index, connection in enumerate(junction.get("connections", []), start=1):
            road = roads_by_id.get(connection.get("roadId"))
            if not road:
                continue
            points = connector_stub_points(junction, road, str(connection.get("endpoint") or "start"))
            if len(points) < 2:
                continue
            gap = math.hypot(points[0]["x"] - float(junction["x"]), points[0]["y"] - float(junction["y"]))
            stub_length = 0.0
            for a, b in zip(points, points[1:]):
                stub_length += math.hypot(float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"]))
            stub = {
                "id": f"{road.get('id')}_{index}_{conn_index}",
                "points": points,
                "width_m": road.get("width_m") or 4.0,
            }
            make_roadbed_mesh(stub, x_shift, mat, floor, name_prefix="junction_connector")
            stubs += 1
            junction_check["connectors"].append(
                {
                    "roadId": road.get("id"),
                    "endpoint": connection.get("endpoint") or "",
                    "startGapM": round(gap, 4),
                    "stubLengthM": round(stub_length, 3),
                    "surfaceOverlapsPad": gap <= pad_radius,
                }
            )
        junction_check["surfaceOverlapPass"] = all(conn["surfaceOverlapsPad"] for conn in junction_check["connectors"])
        checks.append(junction_check)
    surface_overlap_pass = all(check["surfaceOverlapPass"] for check in checks)
    return {
        "junctionPads": pads,
        "connectorStubs": stubs,
        "continuity": {
            "validationType": "surface overlap between pad and connector stubs; not shared-vertex or boolean-unioned mesh connectivity",
            "surfaceOverlapPass": surface_overlap_pass,
            "mergedMeshConnectivityTested": False,
            "checks": checks,
        },
    }


def nearby_roads(data: Dict[str, Any], selected: Dict[str, Any], bounds: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
    roads = []
    selected_id = selected.get("id")
    for road in data.get("roads", []):
        if road.get("id") == selected_id:
            continue
        pts = road.get("points") or []
        if any(in_bounds_xy(point, bounds) for point in pts):
            roads.append(road)
    return roads[:80]


def nearby_buildings(data: Dict[str, Any], bounds: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
    buildings = []
    for building in data.get("buildings", []):
        footprint = building.get("footprint") or []
        if any(in_bounds_xy(point, bounds) for point in footprint):
            buildings.append(building)
    return buildings[:120]


def make_building(building: Dict[str, Any], x_shift: float, mat: bpy.types.Material, floor: float, index: int) -> None:
    footprint = building.get("footprint") or []
    if len(footprint) < 3:
        return
    base_z = sum(norm_z(float(p.get("z") or floor), floor, 0.35) for p in footprint) / len(footprint)
    base = [(float(p["x"]) + x_shift, float(p["y"]), base_z) for p in footprint]
    if (base[0][0] - base[-1][0]) ** 2 + (base[0][1] - base[-1][1]) ** 2 < 0.5:
        base = base[:-1]
    if len(base) < 3:
        return
    height = min(max(float(building.get("height_m") or 6.5), 2.5), 28.0)
    top = [(x, y, z + height) for x, y, z in base]
    verts = base + top
    n = len(base)
    faces = [tuple(range(n)), tuple(range(n, n * 2))]
    for i in range(n):
        faces.append((i, (i + 1) % n, (i + 1) % n + n, i + n))
    mesh = bpy.data.meshes.new(f"ab_building_{index:03d}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f"ab_building_{index:03d}", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)


def add_label(text: str, location: Tuple[float, float, float], size: float = 5.0) -> None:
    bpy.ops.object.text_add(location=location, rotation=(0, 0, 0))
    obj = bpy.context.object
    obj.name = "ab_label_" + text[:18].replace(" ", "_")
    obj.data.body = text
    obj.data.align_x = "CENTER"
    obj.data.size = size


def setup_camera(bounds: Tuple[float, float, float, float], shifts: List[float]) -> None:
    min_x, min_y, max_x, max_y = bounds
    full_min_x = min(min_x + shift for shift in shifts)
    full_max_x = max(max_x + shift for shift in shifts)
    center_x = (full_min_x + full_max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    span_x = full_max_x - full_min_x
    span_y = max_y - min_y
    bpy.ops.object.light_add(type="SUN", location=(center_x, center_y, 300))
    sun = bpy.context.object
    sun.name = "ab_sun_key"
    sun.data.energy = 3.4
    sun.rotation_euler = (math.radians(35), 0, math.radians(35))
    bpy.ops.object.camera_add(location=(center_x, center_y, 820), rotation=(0, 0, 0))
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(span_x, span_y) * 1.08
    bpy.context.scene.camera = camera
    bpy.context.scene.render.resolution_x = 2600
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.eevee.taa_render_samples = 32
    bpy.context.scene.world.color = (0.015, 0.025, 0.035)


def write_report(
    data: Dict[str, Any],
    corridor: Dict[str, Any],
    split_corridor: Dict[str, Any],
    junctions: List[Dict[str, Any]],
    junction_geometry: Dict[str, int],
    bounds: Tuple[float, float, float, float],
    nearby_road_count: int,
    nearby_building_count: int,
    output_prefix: str,
) -> None:
    REPORT_OUT.mkdir(parents=True, exist_ok=True)
    metrics = corridor["corridorMetrics"]
    report = {
        "area": data["area"],
        "selectedCorridor": {
            "osmWayId": corridor.get("id"),
            "name": corridor.get("name") or "",
            "highway": corridor.get("highway"),
            "widthM": corridor.get("width_m"),
            "pointCount": len(corridor.get("points") or []),
            "lengthM": round(metrics["length_m"], 2),
            "reliefM": round(metrics["relief_m"], 2),
            "meanReliefGrade": round(metrics["grade"], 4),
        },
        "corridorProfile": road_profile_summary(corridor),
        "cropBoundsMeters": {
            "minX": round(bounds[0], 2),
            "minY": round(bounds[1], 2),
            "maxX": round(bounds[2], 2),
            "maxY": round(bounds[3], 2),
        },
        "generated": {
            "baselinePanel": "curve road with bevel depth",
            "variantPanel": "terrain-following roadbed ribbon mesh",
            "flattenedPanel": "terrain-flattened roadbed ribbon with first-order graph-node junction geometry",
            "nearbyRoads": nearby_road_count,
            "nearbyBuildings": nearby_building_count,
            "junctionCandidates": len(junctions),
            "splitCorridorPointCount": len(split_corridor.get("points") or []),
            "junctionPads": int(junction_geometry.get("junctionPads", 0)),
            "connectorStubs": int(junction_geometry.get("connectorStubs", 0)),
        },
        "junctions": junctions,
        "continuity": junction_geometry.get("continuity", {}),
        "limitations": [
            "Flattening is local to the selected corridor and is not yet propagated into full-road graph topology.",
            "Junction geometry is first-order pad-and-stub geometry; it is not yet rule-based road engineering.",
            "Continuity is currently surface-overlap validation, not shared-vertex or boolean-unioned mesh connectivity.",
            "Graph splitting currently recognizes exact crossings plus near-endpoint junction candidates; this corridor has endpoint graph nodes rather than mid-segment crossings.",
            "DEM banding remains visible because source elevation is coarse.",
            "Side-by-side panels duplicate local context for visual comparison only.",
        ],
        "nextCheck": "Replace overlapping pad/stub surfaces with shared-vertex or boolean-unioned junction meshes, then add road-rule-based bend and grade smoothing.",
    }
    (REPORT_OUT / f"{output_prefix}_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).resolve()
    output_prefix = str(args.output_prefix).strip() or "corridor_abc"
    BLENDER_OUT.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.mkdir(parents=True, exist_ok=True)
    data = load_dataset(dataset_path)
    corridor = select_corridor(data)
    junctions = find_corridor_junctions(data, corridor, tolerance_m=8.0)
    split_corridor = split_corridor_by_junctions(corridor, junctions)
    bounds = bounds_for_points(corridor["points"], padding=85.0)
    roads = nearby_roads(data, corridor, bounds)
    buildings = nearby_buildings(data, bounds)
    floor = z_min(data)

    reset_scene()
    terrain_mat = material("ab_terrain_matte", (0.10, 0.24, 0.17, 1.0))
    context_road_mat = material("ab_context_roads", (0.08, 0.34, 0.42, 1.0), emission=0.10)
    baseline_mat = material("ab_baseline_curve", (0.12, 0.72, 0.95, 1.0), emission=0.40)
    roadbed_mat = material("ab_roadbed_ribbon", (0.92, 0.78, 0.34, 1.0), emission=0.28)
    flattened_mat = material("ab_flattened_roadbed", (0.98, 0.88, 0.48, 1.0), emission=0.36)
    junction_mat = material("ab_junction_geometry", (1.0, 0.58, 0.18, 1.0), emission=0.62)
    building_mat = material("ab_building_context", (0.55, 0.52, 0.47, 1.0))
    roads_by_id = {road.get("id"): road for road in data.get("roads", [])}

    panel_gap = max(bounds[2] - bounds[0], 220.0) + 135.0
    left_shift = -panel_gap
    middle_shift = 0.0
    right_shift = panel_gap
    flatten_profile = {
        "points": split_corridor["points"],
        "junctions": junctions,
        "halfWidthM": max(float(corridor.get("width_m") or 4.0) / 2.0 + 1.6, 4.2),
        "blendWidthM": 8.0,
        "junctionRadiusM": 7.0,
        "junctionBlendM": 5.0,
        "cutDepthM": 0.22,
    }

    for shift, name, profile in (
        (left_shift, "ab_baseline_terrain", None),
        (middle_shift, "ab_roadbed_terrain", None),
        (right_shift, "ab_flattened_terrain", flatten_profile),
    ):
        make_terrain_panel(data, bounds, shift, terrain_mat, name, profile)
        for road in roads:
            try:
                make_curve_road(road, shift, context_road_mat, floor, f"context_{name}", width_scale=0.025)
            except Exception:
                continue
        for index, building in enumerate(buildings, start=1):
            make_building(building, shift, building_mat, floor, index)

    make_curve_road(corridor, left_shift, baseline_mat, floor, "baseline_curve", width_scale=0.11)
    make_curve_road(corridor, middle_shift, context_road_mat, floor, "variant_centerline", width_scale=0.025)
    make_roadbed_mesh(corridor, middle_shift, roadbed_mat, floor, name_prefix="roadbed_raw")
    make_curve_road(split_corridor, right_shift, context_road_mat, floor, "flattened_centerline", width_scale=0.025)
    make_roadbed_mesh(split_corridor, right_shift, flattened_mat, floor, name_prefix="roadbed_flattened")
    junction_geometry = make_junction_geometry(junctions, roads_by_id, right_shift, junction_mat, floor)

    label_y = bounds[3] + 22.0
    add_label("A: curve baseline", ((bounds[0] + bounds[2]) / 2.0 + left_shift, label_y, 35.0), size=5.0)
    add_label("B: roadbed ribbon", ((bounds[0] + bounds[2]) / 2.0 + middle_shift, label_y, 35.0), size=5.0)
    add_label("C: split + flattened", ((bounds[0] + bounds[2]) / 2.0 + right_shift, label_y, 35.0), size=5.0)
    setup_camera(bounds, [left_shift, middle_shift, right_shift])
    write_report(
        data,
        corridor,
        split_corridor,
        junctions,
        junction_geometry,
        bounds,
        len(roads),
        len(buildings),
        output_prefix,
    )

    blend_path = BLENDER_OUT / f"{output_prefix}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(json.dumps({
        "blend": str(blend_path),
        "dataset": str(dataset_path),
        "selectedWay": corridor.get("id"),
        "junctionCandidates": len(junctions),
        "junctionPads": junction_geometry["junctionPads"],
        "connectorStubs": junction_geometry["connectorStubs"],
        "nearbyRoads": len(roads),
        "nearbyBuildings": len(buildings),
        "report": str(REPORT_OUT / f"{output_prefix}_report.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
