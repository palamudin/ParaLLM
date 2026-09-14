# Source Map

## Blender

- Blender 5.0 release notes: https://developer.blender.org/docs/release_notes/5.0/
- Blender 5.1 release notes: https://developer.blender.org/docs/release_notes/5.1/
- Blender 5.0 Geometry Nodes release notes: https://developer.blender.org/docs/release_notes/5.0/geometry_nodes/
- Blender 5.0 EEVEE and viewport notes: https://developer.blender.org/docs/release_notes/5.0/eevee/
- Current Blender Python `bpy.types.Curve` API: https://docs.blender.org/api/current/bpy.types.Curve.html
- Current Blender Python curve operators: https://docs.blender.org/api/current/bpy.ops.curve.html
- Current Blender Python API landing page: https://docs.blender.org/api/current/

## GIS, Terrain, and Open Data

- OpenStreetMap Overpass QL reference: https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
- Overpass API examples: https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_API_by_Example
- DataSF Streets Active and Retired centerlines: https://data.sfgov.org/Geographic-Locations-and-Boundaries/Streets-Active-and-Retired/3psu-pn9h
- DataSF Socrata API endpoint for street centerlines: https://data.sfgov.org/resource/3psu-pn9h.json
- Open-Meteo Elevation API: https://open-meteo.com/en/docs/elevation-api
- Open-Elevation API: https://api.open-elevation.com/api/v1/lookup
- OpenTopoData SRTM90m API: https://api.opentopodata.org/v1/srtm90m
- OpenTopography developer/API overview: https://opentopography.org/developers
- Mapzen/AWS terrain tile Terrarium format notes: https://www.mapzen.com/blog/terrain-tile-service/
- Microsoft Global ML Building Footprints: https://github.com/microsoft/GlobalMLBuildingFootprints
- OpenBuildingMap global building footprint dataset: https://www.openbuildingmap.org/

## Blender GIS and Road Add-on References

- BlenderGIS: https://blendergis.com/
- BlenderGIS repository: https://github.com/domlysz/BlenderGIS
- Roadscape product reference: https://blendatlas.com/products/roadscape

## Practical Notes

- Public Overpass endpoints are shared infrastructure. Keep bounding boxes small, use conservative timeouts, and cache outputs.
- Open-Meteo elevation accepts multiple coordinates, but the public endpoint should be chunked politely.
- OpenTopography has stronger DEM options but often needs an API key for production throughput.
