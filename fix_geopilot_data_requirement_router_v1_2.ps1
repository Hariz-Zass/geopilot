
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================"
Write-Host "GeoPilot Data Requirement Router Policy Precedence Fix V1.2"
Write-Host "Fixes terrain policy vs terrain measurement classification"
Write-Host "============================================================"
Write-Host ""

$router = ".\backend\app\services\data_requirement_router.py"
if (-not (Test-Path $router)) {
    throw "data_requirement_router.py not found"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = ".\artifacts\data_requirement_router_v1_2_backup_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $router "$backup\data_requirement_router.py"

$text = Get-Content $router -Raw

$old = @'
    terrain = _contains_any(q, _TERRAIN_TERMS)
    terrain_measurement = terrain and (
        _contains_any(q, _TERRAIN_MEASUREMENT_TERMS)
        or _contains_any(q, _SITE_APPLICABILITY_TERMS)
    )
    terrain_policy = terrain and _contains_any(q, _POLICY_TERMS)

    if terrain_policy and not terrain_measurement:
'@

$new = @'
    terrain = _contains_any(q, _TERRAIN_TERMS)
    terrain_policy = terrain and _contains_any(q, _POLICY_TERMS)
    terrain_measurement = terrain and (
        _contains_any(q, _TERRAIN_MEASUREMENT_TERMS)
        or _contains_any(q, _SITE_APPLICABILITY_TERMS)
    )

    # Policy intent takes precedence over site words such as "applies".
    # Example: "What guideline applies to slope development?" is a
    # controlled document-retrieval question, not a request to measure slope.
    if terrain_policy:
'@

if (-not $text.Contains($old)) {
    throw "Expected terrain routing block not found; STOP to avoid blind patch."
}

$text = $text.Replace($old, $new)
Set-Content -Path $router -Value $text -Encoding UTF8

Write-Host "BACKUP: $backup"
Write-Host "PATCHED: $router"

Write-Host ""
Write-Host "[1/5] Python compile gate..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend backend python -m compileall app/services/data_requirement_router.py app/services/planning_orchestrator.py tests/test_data_requirement_router.py
if ($LASTEXITCODE -ne 0) { throw "Compile gate failed" }

Write-Host ""
Write-Host "[2/5] Router regression tests..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend backend pytest -q tests/test_data_requirement_router.py
if ($LASTEXITCODE -ne 0) { throw "Router regression failed" }

Write-Host ""
Write-Host "[3/5] Existing Track B regression baseline..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend backend pytest -q tests/test_track_b_hackathon.py
if ($LASTEXITCODE -ne 0) { throw "Track B regression failed" }

Write-Host ""
Write-Host "[4/5] Recreating backend only..."
docker compose up -d --force-recreate backend
if ($LASTEXITCODE -ne 0) { throw "Backend recreate failed" }

Write-Host ""
Write-Host "[5/5] Runtime classification verification..."
Start-Sleep -Seconds 4
docker compose exec -T backend python -c "from app.services.data_requirement_router import route_question; a=route_question('berapa slope tertinggi di kawasan ini'); b=route_question('What guideline applies to slope development?'); print('MEASURE:',a.state,a.capability,list(a.required_evidence)); print('POLICY:',b.state,b.capability,list(b.tools)); assert a.state=='evidence_required'; assert b.state=='planned'; assert b.tools==('documents.search',)"
if ($LASTEXITCODE -ne 0) { throw "Runtime classification verification failed" }

Write-Host ""
Write-Host "============================================================"
Write-Host "DATA REQUIREMENT ROUTER V1.2 GATE PASS"
Write-Host "Measured terrain questions require DEM."
Write-Host "Terrain policy questions route to controlled documents."
Write-Host "Track B regression baseline remains green."
Write-Host "============================================================"
