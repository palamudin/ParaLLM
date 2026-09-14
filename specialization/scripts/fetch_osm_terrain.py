from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import requests


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Specialization" / "output"
DATA_OUT = OUT / "data"


@dataclass(frozen=True)
class CandidateArea:
    name: str
    country: str
    lat: float
    lon: float
    half_span_deg: float
    reason: str


CANDIDATES = [
    CandidateArea("Bled", "Slovenia", 46.3639, 14.0943, 0.0075, "compact roads, buildings, lake-edge terrain"),
    CandidateArea("Kotor", "Montenegro", 42.4247, 18.7712, 0.0065, "steep terrain, old town roads, dense buildings"),
    CandidateArea("Otaru", "Japan", 43.1977, 140.9947, 0.0065, "coastal hillside urban roads"),
    CandidateArea("Queenstown", "New Zealand", -45.0312, 168.6626, 0.0065, "mountain town roads and terrain"),
    CandidateArea("Sintra", "Portugal", 38.8029, -9.3817, 0.0070, "hilly historic roads and buildings"),
]

ROAD_WIDTHS = {
    "motorway": 14.0,
    "trunk": 12.0,
    "primary": 11.0,
    "secondary": 9.0,
    "tertiary": 8.0,
    "unclassified": 6.0,
    "residential": 5.5,
    "living_street": 4.5,
    "service": 3.5,
    "track": 3.0,
    "path": 2.0,
    "footway": 1.8,
    "cycleway": 2.0,
}


def choose_area() -> CandidateArea:
    seed = int(time.time())
    rng = random.Random(seed)
    area = rng.choice(CANDIDATES)
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    (DATA_OUT / "area_seed.json").write_text(
        json.dumps({"seed": seed, "selected": area.__dict__}, indent=2),
        encoding="utf-8",
    )
    return area


def bbox(area: CandidateArea) -> Tuple[float, float, float, float]:
    return (
        area.lat - area.half_span_deg,
        area.lon - area.half_span_deg,
        area.lat + area.half_span_deg,
        area.lon + area.half_span_deg,
    )


def overpass_query(area: CandidateArea) -> Dict[str, Any]:
    south, west, north, east = bbox(area)
    query = f"""
[out:json][timeout:35];
(
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|track|path|footway|cycleway)$"]({south},{west},{north},{east});
  way["building"]({south},{west},{north},{east});
  node["place"]({south},{west},{north},{east});
  node["population"]({south},{west},{north},{east});
  way["population"]({south},{west},{north},{east});
  relation["population"]({south},{west},{north},{east});
);
out tags geom;
"""
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.openstreetmap.ru/api/interpreter",
    ]
    headers = {
        "User-Agent": "ParaLLM-specialization-terrain-proof/0.1 (small bbox research run)",
        "Accept": "application/json",
    }
    last_error = None
    for url in endpoints:
        try:
            response = requests.post(url, data={"data": query}, headers=headers, timeout=90)
            if response.status_code == 406:
                response = requests.get(url, params={"data": query}, headers=headers, timeout=90)
            response.raise_for_status()
            payload = response.json()
            payload["_query"] = query
            payload["_source"] = url
            return payload
        except Exception as exc:  # endpoint rotation records the final error below
            last_error = exc
            time.sleep(1.0)
    raise RuntimeError(f"All Overpass endpoints failed. Last error: {last_error}")


def chunked(items: List[Any], size: int) -> Iterable[List[Any]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def fetch_open_meteo_elevation(coords: List[Tuple[float, float]]) -> Tuple[List[float], str, str]:
    elevations: List[float] = []
    url = "https://api.open-meteo.com/v1/elevation"
    for part in chunked(coords, 100):
        params = {
            "latitude": ",".join(f"{lat:.7f}" for lat, _ in part),
            "longitude": ",".join(f"{lon:.7f}" for _, lon in part),
        }
        response = requests.get(url, params=params, timeout=45)
        response.raise_for_status()
        data = response.json()
        elevations.extend(float(value) for value in data["elevation"])
        time.sleep(0.15)
    return elevations, url, "Open-Meteo Elevation API; Copernicus DEM GLO-90 per provider docs"


def fetch_open_elevation(coords: List[Tuple[float, float]]) -> Tuple[List[float], str, str]:
    elevations: List[float] = []
    url = "https://api.open-elevation.com/api/v1/lookup"
    for part in chunked(coords, 80):
        payload = {
            "locations": [
                {"latitude": round(lat, 7), "longitude": round(lon, 7)}
                for lat, lon in part
            ]
        }
        response = requests.post(url, json=payload, timeout=45)
        response.raise_for_status()
        data = response.json()
        results = data.get("results") or []
        if len(results) != len(part):
            raise RuntimeError(f"Open-Elevation returned {len(results)} results for {len(part)} coordinates")
        elevations.extend(float(item["elevation"]) for item in results)
        time.sleep(0.2)
    return elevations, url, "Open-Elevation API; public DEM aggregation per provider"


def fetch_opentopodata(coords: List[Tuple[float, float]]) -> Tuple[List[float], str, str]:
    elevations: List[float] = []
    url = "https://api.opentopodata.org/v1/srtm90m"
    for part in chunked(coords, 80):
        params = {
            "locations": "|".join(f"{lat:.7f},{lon:.7f}" for lat, lon in part),
        }
        response = requests.get(url, params=params, timeout=45)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "OK":
            raise RuntimeError(f"OpenTopoData returned status {data.get('status')}")
        results = data.get("results") or []
        if len(results) != len(part):
            raise RuntimeError(f"OpenTopoData returned {len(results)} results for {len(part)} coordinates")
        elevations.extend(float(item["elevation"]) for item in results)
        time.sleep(0.2)
    return elevations, url, "OpenTopoData SRTM 90m public dataset"


def elevation_grid(area: CandidateArea, samples: int = 25) -> Dict[str, Any]:
    south, west, north, east = bbox(area)
    lats = [south + (north - south) * i / (samples - 1) for i in range(samples)]
    lons = [west + (east - west) * i / (samples - 1) for i in range(samples)]
    coords = [(lat, lon) for lat in lats for lon in lons]
    providers = [
        fetch_open_meteo_elevation,
        fetch_open_elevation,
        fetch_opentopodata,
    ]
    last_error = None
    for provider in providers:
        try:
            elevations, source, dataset = provider(coords)
            break
        except Exception as exc:
            last_error = exc
            print(f"Elevation provider {provider.__name__} failed: {exc}")
    else:
        raise RuntimeError(f"All elevation providers failed. Last error: {last_error}")
    grid = []
    cursor = 0
    for _lat in lats:
        row = []
        for _lon in lons:
            row.append(elevations[cursor])
            cursor += 1
        grid.append(row)
    return {
        "source": source,
        "dataset": dataset,
        "samples": samples,
        "lats": lats,
        "lons": lons,
        "grid": grid,
    }


def project(lat: float, lon: float, lat0: float, lon0: float) -> Tuple[float, float]:
    meters_per_deg_lat = 110_574.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    x = (lon - lon0) * meters_per_deg_lon
    y = (lat - lat0) * meters_per_deg_lat
    return x, y


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


def normalize_payload(area: CandidateArea, osm: Dict[str, Any], elev: Dict[str, Any]) -> Dict[str, Any]:
    lat0 = area.lat
    lon0 = area.lon
    roads = []
    buildings = []
    places = []
    node_degree: Dict[str, int] = {}

    for element in osm.get("elements", []):
        tags = element.get("tags") or {}
        geom = element.get("geometry") or []
        if element.get("type") == "way" and tags.get("highway") and len(geom) >= 2:
            points = []
            for point in geom:
                lat = float(point["lat"])
                lon = float(point["lon"])
                x, y = project(lat, lon, lat0, lon0)
                z = bilinear_elevation(lat, lon, elev)
                points.append({"lat": lat, "lon": lon, "x": x, "y": y, "z": z})
            for key in (f"{points[0]['lat']:.6f},{points[0]['lon']:.6f}", f"{points[-1]['lat']:.6f},{points[-1]['lon']:.6f}"):
                node_degree[key] = node_degree.get(key, 0) + 1
            highway = str(tags.get("highway") or "road")
            roads.append({
                "id": element.get("id"),
                "name": tags.get("name") or "",
                "highway": highway,
                "width_m": ROAD_WIDTHS.get(highway, 4.0),
                "oneway": tags.get("oneway") or "",
                "maxspeed": tags.get("maxspeed") or "",
                "points": points,
                "tags": tags,
            })
        elif element.get("type") == "way" and tags.get("building") and len(geom) >= 3:
            footprint = []
            for point in geom:
                lat = float(point["lat"])
                lon = float(point["lon"])
                x, y = project(lat, lon, lat0, lon0)
                z = bilinear_elevation(lat, lon, elev)
                footprint.append({"lat": lat, "lon": lon, "x": x, "y": y, "z": z})
            height = parse_height(tags)
            buildings.append({
                "id": element.get("id"),
                "height_m": height,
                "building": tags.get("building") or "yes",
                "levels": tags.get("building:levels") or "",
                "footprint": footprint,
                "tags": tags,
            })
        elif element.get("type") in {"node", "way", "relation"} and (tags.get("place") or tags.get("population")):
            places.append({
                "id": element.get("id"),
                "type": element.get("type"),
                "name": tags.get("name") or "",
                "place": tags.get("place") or "",
                "population": tags.get("population") or "",
                "tags": tags,
            })

    junctions = []
    for road in roads:
        for endpoint in (road["points"][0], road["points"][-1]):
            key = f"{endpoint['lat']:.6f},{endpoint['lon']:.6f}"
            if node_degree.get(key, 0) >= 3:
                junctions.append({**endpoint, "degree": node_degree[key]})

    return {
        "area": area.__dict__,
        "bbox": {
            "south": bbox(area)[0],
            "west": bbox(area)[1],
            "north": bbox(area)[2],
            "east": bbox(area)[3],
        },
        "projection": {
            "type": "local_equirectangular_meters",
            "lat0": lat0,
            "lon0": lon0,
        },
        "sources": {
            "osm": osm.get("_source"),
            "overpassQuery": osm.get("_query"),
            "elevation": elev["source"],
            "elevationDataset": elev["dataset"],
        },
        "elevation": elev,
        "roads": roads,
        "buildings": buildings,
        "places": places,
        "junctions": dedupe_junctions(junctions),
        "summary": {
            "roadCount": len(roads),
            "buildingCount": len(buildings),
            "placePopulationRecords": len(places),
            "junctionCount": len(dedupe_junctions(junctions)),
        },
    }


def parse_height(tags: Dict[str, str]) -> float:
    raw_height = str(tags.get("height") or "").lower().replace("m", "").strip()
    try:
        value = float(raw_height)
        if 1.0 <= value <= 200.0:
            return value
    except ValueError:
        pass
    raw_levels = str(tags.get("building:levels") or "").strip()
    try:
        levels = float(raw_levels)
        if 0.5 <= levels <= 80.0:
            return max(3.0, levels * 3.1)
    except ValueError:
        pass
    return 6.5


def dedupe_junctions(junctions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for point in junctions:
        key = f"{point['lat']:.6f},{point['lon']:.6f}"
        seen[key] = point
    return list(seen.values())


def main() -> None:
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    area = choose_area()
    osm = overpass_query(area)
    elev = elevation_grid(area)
    normalized = normalize_payload(area, osm, elev)
    raw_path = DATA_OUT / "osm_raw.json"
    terrain_path = DATA_OUT / "terrain_roads_dataset.json"
    raw_path.write_text(json.dumps(osm, indent=2), encoding="utf-8")
    terrain_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    print(json.dumps({
        "selectedArea": area.__dict__,
        "dataset": str(terrain_path),
        "summary": normalized["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
