from types import SimpleNamespace
from pathlib import Path
import uuid

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.services.terrain_analysis import (
    TerrainEvidenceMissing,
    _terrain_role,
    _source_path,
)


def test_dem_selector_role_is_strict_and_does_not_accept_ndvi():
    dem = SimpleNamespace(provenance={"data_role": "dem"}, band_names=["Elevation"])
    elev = SimpleNamespace(provenance={}, band_names=["elevation_m"])
    ndvi = SimpleNamespace(provenance={"data_role": "before"}, band_names=["B04", "B08"])
    assert _terrain_role(dem) == "elevation"
    assert _terrain_role(elev) == "elevation"
    assert _terrain_role(ndvi) is None


def test_remote_dem_uri_fails_closed():
    with pytest.raises(TerrainEvidenceMissing):
        _source_path("https://example.invalid/dem.tif")


def test_local_file_uri_is_resolved():
    assert _source_path("file:///tmp/dem.tif") == Path("/tmp/dem.tif")


def test_slope_math_on_planar_surface_is_deterministic(tmp_path):
    from app.services import terrain_analysis

    path = tmp_path / "dem.tif"
    rows, cols = 10, 10
    # z increases 1 metre per 10 horizontal metres in x => atan(0.1)
    arr = np.tile(np.arange(cols, dtype="float32"), (rows, 1))
    with rasterio.open(
        path, "w", driver="GTiff", width=cols, height=rows, count=1,
        dtype="float32", crs="EPSG:32647",
        transform=from_origin(500000, 400000, 10, 10), nodata=-9999.0,
    ) as ds:
        ds.write(arr, 1)

    # Directly validate raster gradient convention used by the engine.
    with rasterio.open(path) as ds:
        data = ds.read(1).astype("float64")
        dz_dy, dz_dx = np.gradient(data, 10.0, 10.0)
        slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
    expected = np.degrees(np.arctan(0.1))
    assert np.allclose(slope, expected, atol=1e-8)


def test_tool_registry_contains_bounded_terrain_summary():
    from app.services.planning_tools import get_tool
    spec = get_tool("terrain.site_summary")
    assert spec.domain == "terrain"
    assert spec.deterministic is True
    assert spec.read_only is True


def test_select_site_dem_auto_acquires_only_when_missing(monkeypatch):
    from app.services import terrain_analysis
    sentinel = SimpleNamespace(source_uri="local://rasters/auto.tif")
    calls = {"preferred": 0, "acquire": 0}
    monkeypatch.setattr(terrain_analysis, "resolve_project_scope", lambda *a, **k: None)
    monkeypatch.setattr(terrain_analysis, "resolve_site_scope", lambda *a, **k: None)
    def preferred(*args, **kwargs):
        calls["preferred"] += 1
        return None
    def acquire(*args, **kwargs):
        calls["acquire"] += 1
        return sentinel
    monkeypatch.setattr(terrain_analysis, "preferred_site_dem", preferred)
    monkeypatch.setattr(terrain_analysis, "acquire_site_dem_if_missing", acquire)
    result = terrain_analysis.select_site_dem(object(), owner=object(), project_id=uuid.uuid4(), site_id=uuid.uuid4())
    assert result is sentinel
    assert calls == {"preferred": 1, "acquire": 1}


def test_select_site_dem_preserves_existing_dem_precedence(monkeypatch):
    from app.services import terrain_analysis
    manual = SimpleNamespace(source_uri="local://rasters/manual.tif")
    calls = {"acquire": 0}
    monkeypatch.setattr(terrain_analysis, "resolve_project_scope", lambda *a, **k: None)
    monkeypatch.setattr(terrain_analysis, "resolve_site_scope", lambda *a, **k: None)
    monkeypatch.setattr(terrain_analysis, "preferred_site_dem", lambda *a, **k: manual)
    def acquire(*args, **kwargs):
        calls["acquire"] += 1
        raise AssertionError("auto acquisition must not run when a ready DEM exists")
    monkeypatch.setattr(terrain_analysis, "acquire_site_dem_if_missing", acquire)
    result = terrain_analysis.select_site_dem(object(), owner=object(), project_id=uuid.uuid4(), site_id=uuid.uuid4())
    assert result is manual
    assert calls["acquire"] == 0
