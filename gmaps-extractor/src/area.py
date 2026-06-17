import json
from dataclasses import dataclass, asdict
from pathlib import Path

import geopandas as gpd
import h3
from shapely.geometry import box, mapping


@dataclass
class CellInfo:
    id: str
    lat: float
    lng: float


def load_polygon(path: str | Path):
    """Read a GeoJSON or Shapefile and return the unified polygon geometry."""
    gdf = gpd.read_file(path)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf.union_all()


def bbox_to_polygon(lat_min: float, lat_max: float, lng_min: float, lng_max: float):
    return box(lng_min, lat_min, lng_max, lat_max)


def build_hex_grid(polygon, resolution: int = 9) -> list[CellInfo]:
    """Fill a polygon with H3 hex cells at given resolution, return their centers."""
    geojson = mapping(polygon)

    # h3 v4 API: convert geojson polygon to h3 LatLngPoly then polyfill
    # coords may be 2D or 3D (shapefiles often include Z), so use indexing
    def _to_latlng(ring):
        return [(pt[1], pt[0]) for pt in ring]

    if geojson["type"] == "MultiPolygon":
        all_cells = set()
        for coords in geojson["coordinates"]:
            outer = _to_latlng(coords[0])
            holes = [_to_latlng(ring) for ring in coords[1:]]
            poly = h3.LatLngPoly(outer, *holes)
            all_cells.update(h3.polygon_to_cells(poly, resolution))
    else:
        outer = _to_latlng(geojson["coordinates"][0])
        holes = [_to_latlng(ring) for ring in geojson["coordinates"][1:]]
        poly = h3.LatLngPoly(outer, *holes)
        all_cells = set(h3.polygon_to_cells(poly, resolution))

    cells = []
    for cell_id in sorted(all_cells):
        lat, lng = h3.cell_to_latlng(cell_id)
        cells.append(CellInfo(id=cell_id, lat=round(lat, 7), lng=round(lng, 7)))

    return cells


def preview_grid(polygon, resolution: int = 9) -> dict:
    cells = build_hex_grid(polygon, resolution)
    avg_area_km2 = h3.cell_area(cells[0].id, unit="km^2") if cells else 0
    total_area_km2 = avg_area_km2 * len(cells)
    return {
        "resolution": resolution,
        "cell_count": len(cells),
        "avg_cell_area_km2": round(avg_area_km2, 6),
        "total_coverage_km2": round(total_area_km2, 2),
    }


def save_area_manifest(cells: list[CellInfo], resolution: int, path: str | Path, source: str = ""):
    manifest = {
        "resolution": resolution,
        "cell_count": len(cells),
        "source": source,
        "cells": [asdict(c) for c in cells],
    }
    Path(path).write_text(json.dumps(manifest, indent=2))


def load_area_manifest(path: str | Path) -> tuple[list[CellInfo], dict]:
    data = json.loads(Path(path).read_text())
    cells = [CellInfo(**c) for c in data["cells"]]
    meta = {k: v for k, v in data.items() if k != "cells"}
    return cells, meta
