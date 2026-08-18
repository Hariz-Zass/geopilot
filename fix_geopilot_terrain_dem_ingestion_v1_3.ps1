
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================"
Write-Host "GeoPilot Terrain DEM Ingestion Test Recovery V1.3"
Write-Host "Creates missing regression test file after earlier guarded stop"
Write-Host "NO source rewrite beyond tests - Track B protected"
Write-Host "============================================================"
Write-Host ""

$test = ".\backend\tests\test_terrain_ingestion.py"
$service = ".\backend\app\services\terrain_ingestion.py"
$api = ".\backend\app\api\v1\terrain.py"
$router = ".\backend\app\api\v1\router.py"

foreach ($f in @($service, $api, $router)) {
    if (-not (Test-Path $f)) {
        throw "Required file missing: $f"
    }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = ".\artifacts\terrain_ingestion_v1_3_backup_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
if (Test-Path $test) {
    Copy-Item $test "$backup\test_terrain_ingestion.py"
}

$testContent = @'
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
'@

Set-Content -Path $test -Value $testContent -Encoding UTF8
Write-Host "BACKUP: $backup"
Write-Host "WROTE: $test"

Write-Host ""
Write-Host "[1/6] Exact router registration audit..."
$routerText = Get-Content $router -Raw
if ($routerText -notmatch 'from app\.api\.v1\.terrain import router as terrain_router') {
    throw "terrain_router import is not present in router.py"
}
if ($routerText -notmatch 'api_router\.include_router\(terrain_router\)') {
    throw "terrain_router include is not present in router.py"
}
Write-Host "ROUTER REGISTRATION: PASS"

Write-Host ""
Write-Host "[2/6] Compile gate..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend backend python -m compileall app/api/v1/router.py app/api/v1/terrain.py app/services/terrain_ingestion.py tests/test_terrain_ingestion.py
if ($LASTEXITCODE -ne 0) { throw "Compile gate failed" }

Write-Host ""
Write-Host "[3/6] DEM ingestion + Terrain Engine tests..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend backend pytest -q tests/test_terrain_ingestion.py tests/test_terrain_analysis.py
if ($LASTEXITCODE -ne 0) { throw "Terrain tests failed" }

Write-Host ""
Write-Host "[4/6] Data Requirement Router regression..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend backend pytest -q tests/test_data_requirement_router.py
if ($LASTEXITCODE -ne 0) { throw "Router regression failed" }

Write-Host ""
Write-Host "[5/6] Track B regression baseline..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend backend pytest -q tests/test_track_b_hackathon.py
if ($LASTEXITCODE -ne 0) { throw "Track B regression failed" }

Write-Host ""
Write-Host "[6/6] Recreate backend + runtime verification..."
docker compose up -d --force-recreate backend
if ($LASTEXITCODE -ne 0) { throw "Backend recreate failed" }

Start-Sleep -Seconds 4

docker compose exec -T backend python -c "from app.main import app; from app.services.planning_tools import get_tool; p='/api/v1/projects/{project_id}/sites/{site_id}/terrain/dem'; paths={r.path for r in app.routes}; print('DEM_ROUTE=',p in paths); print('TERRAIN_TOOL=',get_tool('terrain.site_summary')); assert p in paths"
if ($LASTEXITCODE -ne 0) { throw "Runtime verification failed" }

Write-Host ""
Write-Host "============================================================"
Write-Host "TERRAIN DEM INGESTION V1.3 GATE PASS"
Write-Host "Missing test file recovered."
Write-Host "DEM endpoint + terrain engine + router + Track B regressions pass."
Write-Host "============================================================"
