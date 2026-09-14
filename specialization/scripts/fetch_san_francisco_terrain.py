from __future__ import annotations

import json
from pathlib import Path

from fetch_osm_terrain import CandidateArea, elevation_grid, normalize_payload, overpass_query


ROOT = Path(__file__).resolve().parents[2]
DATA_OUT = ROOT / "specialization" / "output" / "data"


def main() -> None:
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    area = CandidateArea(
        "San Francisco",
        "United States",
        37.80215,
        -122.41885,
        0.0048,
        "Russian Hill / Nob Hill steep urban grid, Lombard-adjacent road network",
    )
    osm = overpass_query(area)
    elev = elevation_grid(area, samples=31)
    normalized = normalize_payload(area, osm, elev)
    raw_path = DATA_OUT / "san_francisco_osm_raw.json"
    terrain_path = DATA_OUT / "san_francisco_terrain_roads_dataset.json"
    raw_path.write_text(json.dumps(osm, indent=2), encoding="utf-8")
    terrain_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "selectedArea": area.__dict__,
                "dataset": str(terrain_path),
                "raw": str(raw_path),
                "summary": normalized["summary"],
                "sources": normalized["sources"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
