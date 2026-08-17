import numpy as np
import pytest
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from app.services.terrain_ingestion import (
    TerrainIngestionError,
    _inspect_dem_bytes,
    _metric_projected_crs,
)


def _dem_bytes(*, count: int = 1, crs: str = "EPSG:32647") -> bytes:
    width = height = 20
    transform = from_origin(
        750000.0,
        350000.0,
        10.0,
        10.0,
    )
    arr = np.arange(
        width * height,
        dtype="float32",
    ).reshape(height, width)

    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=width,
            height=height,
            count=count,
            dtype="float32",
            crs=crs,
            transform=transform,
            nodata=-9999.0,
        ) as ds:
            for index in range(1, count + 1):
                ds.write(arr, index)
        return mem.read()


def _site_inside_dem() -> dict:
    to_wgs84 = Transformer.from_crs(
        "EPSG:32647",
        "EPSG:4326",
        always_xy=True,
    )
    left, bottom = to_wgs84.transform(
        750030.0,
        349830.0,
    )
    right, top = to_wgs84.transform(
        750170.0,
        349970.0,
    )
    return {
        "type": "Polygon",
        "coordinates": [[
            [left, bottom],
            [right, bottom],
            [right, top],
            [left, top],
            [left, bottom],
        ]],
    }


def test_metric_projected_crs_accepts_utm_metres():
    assert _metric_projected_crs(
        "EPSG:32647"
    ).is_projected


def test_metric_projected_crs_rejects_geographic():
    with pytest.raises(TerrainIngestionError):
        _metric_projected_crs("EPSG:4326")


def test_dem_inspection_accepts_single_band_metric_geotiff_with_site_coverage():
    inspected = _inspect_dem_bytes(
        _dem_bytes(),
        site_geometry=_site_inside_dem(),
    )
    assert inspected.driver == "GTiff"
    assert inspected.valid_site_pixel_count >= 4
    assert inspected.pixel_size == {
        "x": 10.0,
        "y": 10.0,
    }


def test_dem_inspection_rejects_multiband_raster():
    with pytest.raises(
        TerrainIngestionError,
        match="single-band",
    ):
        _inspect_dem_bytes(
            _dem_bytes(count=2),
            site_geometry=_site_inside_dem(),
        )


def test_terrain_dem_api_surface_is_registered():
    from app.main import app

    paths = {
        route.path
        for route in app.routes
    }
    assert (
        "/api/v1/projects/{project_id}/sites/{site_id}/terrain/dem"
        in paths
    )
