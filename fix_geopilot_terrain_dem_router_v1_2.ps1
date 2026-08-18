
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================"
Write-Host "GeoPilot Terrain DEM Router Registration Fix V1.2"
Write-Host "Exact patch for backend/app/api/v1/router.py"
Write-Host "============================================================"
Write-Host ""

$router = ".\backend\app\api\v1\router.py"
if (-not (Test-Path $router)) {
    throw "router.py not found"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = ".\artifacts\terrain_dem_router_v1_2_backup_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $router "$backup\router.py"

$text = Get-Content $router -Raw

$importLine = "from app.api.v1.terrain import router as terrain_router"
if ($text -notmatch [regex]::Escape($importLine)) {
    $anchor = "from app.api.v1.track_b import router as track_b_router"
    if (-not $text.Contains($anchor)) {
        throw "Exact import anchor not found; STOP."
    }
    $text = $text.Replace(
        $anchor,
        $anchor + "`r`n" + $importLine
    )
}

$includeLine = "api_router.include_router(terrain_router)"
if ($text -notmatch [regex]::Escape($includeLine)) {
    $anchor = "api_router.include_router(track_b_router)"
    if (-not $text.Contains($anchor)) {
        throw "Exact include_router anchor not found; STOP."
    }
    $text = $text.Replace(
        $anchor,
        $anchor + "`r`n" + $includeLine
    )
}

Set-Content -Path $router -Value $text -Encoding UTF8

Write-Host "BACKUP: $backup"
Write-Host "PATCHED: $router"

Write-Host ""
Write-Host "[1/5] Compile gate..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend backend python -m compileall app/api/v1/router.py app/api/v1/terrain.py app/services/terrain_ingestion.py tests/test_terrain_ingestion.py
if ($LASTEXITCODE -ne 0) { throw "Compile gate failed" }

Write-Host ""
Write-Host "[2/5] Terrain ingestion + engine tests..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend backend pytest -q tests/test_terrain_ingestion.py tests/test_terrain_analysis.py
if ($LASTEXITCODE -ne 0) { throw "Terrain tests failed" }

Write-Host ""
Write-Host "[3/5] Router regression..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend backend pytest -q tests/test_data_requirement_router.py
if ($LASTEXITCODE -ne 0) { throw "Router regression failed" }

Write-Host ""
Write-Host "[4/5] Track B regression..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend backend pytest -q tests/test_track_b_hackathon.py
if ($LASTEXITCODE -ne 0) { throw "Track B regression failed" }

Write-Host ""
Write-Host "[5/5] Recreate backend + runtime verify..."
docker compose up -d --force-recreate backend
if ($LASTEXITCODE -ne 0) { throw "Backend recreate failed" }

Start-Sleep -Seconds 4

docker compose exec -T backend python -c "from app.main import app; p='/api/v1/projects/{project_id}/sites/{site_id}/terrain/dem'; paths={r.path for r in app.routes}; print('DEM_ROUTE=',p in paths); assert p in paths"
if ($LASTEXITCODE -ne 0) { throw "DEM route runtime verification failed" }

Write-Host ""
Write-Host "============================================================"
Write-Host "TERRAIN DEM INGESTION V1.2 GATE PASS"
Write-Host "Terrain DEM endpoint is registered through api/v1/router.py."
Write-Host "============================================================"
