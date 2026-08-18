
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================"
Write-Host "GeoPilot Terrain DEM Router Registration Fix V1.1"
Write-Host "Fixes API router registration only"
Write-Host "============================================================"
Write-Host ""

$init = ".\backend\app\api\v1\__init__.py"
if (-not (Test-Path $init)) {
    throw "api/v1/__init__.py not found"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = ".\artifacts\terrain_ingestion_router_fix_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $init "$backup\__init__.py"

$text = Get-Content $init -Raw

if ($text -notmatch 'from app\.api\.v1 import terrain') {
    if ($text -match 'from app\.api\.v1 import \((?<body>[\s\S]*?)\)') {
        $text = [regex]::Replace(
            $text,
            'from app\.api\.v1 import \((?<body>[\s\S]*?)\)',
            {
                param($m)
                $body = $m.Groups['body'].Value.TrimEnd()
                "from app.api.v1 import (" + $body + "`r`n    terrain,`r`n)"
            },
            1
        )
    }
    else {
        $text = "from app.api.v1 import terrain`r`n" + $text
    }
}

if ($text -notmatch 'terrain\.router') {
    if ($text -match 'api_router\.include_router\(') {
        $matches = [regex]::Matches($text, 'api_router\.include_router\([\s\S]*?\)')
        if ($matches.Count -lt 1) {
            throw "No include_router call found"
        }
        $last = $matches[$matches.Count - 1]
        $insertAt = $last.Index + $last.Length
        $text = $text.Substring(0, $insertAt) + "`r`napi_router.include_router(terrain.router)" + $text.Substring($insertAt)
    }
    elseif ($text -match 'router\.include_router\(') {
        $matches = [regex]::Matches($text, 'router\.include_router\([\s\S]*?\)')
        if ($matches.Count -lt 1) {
            throw "No router.include_router call found"
        }
        $last = $matches[$matches.Count - 1]
        $insertAt = $last.Index + $last.Length
        $text = $text.Substring(0, $insertAt) + "`r`nrouter.include_router(terrain.router)" + $text.Substring($insertAt)
    }
    else {
        throw "Could not identify router registration style; STOP to avoid blind patch."
    }
}

Set-Content -Path $init -Value $text -Encoding UTF8
Write-Host "BACKUP: $backup"
Write-Host "PATCHED: $init"

Write-Host ""
Write-Host "[1/5] Compile gate..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend backend python -m compileall app/api/v1/__init__.py app/api/v1/terrain.py app/services/terrain_ingestion.py tests/test_terrain_ingestion.py
if ($LASTEXITCODE -ne 0) { throw "Compile gate failed" }

Write-Host ""
Write-Host "[2/5] DEM ingestion + terrain tests..."
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
Write-Host "TERRAIN DEM INGESTION V1.1 GATE PASS"
Write-Host "Terrain DEM endpoint is registered and runtime-visible."
Write-Host "============================================================"
