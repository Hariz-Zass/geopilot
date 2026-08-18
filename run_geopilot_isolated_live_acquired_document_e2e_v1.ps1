$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Py = Join-Path $Root "run_geopilot_isolated_live_acquired_document_e2e_v1.py"
$BackendPy = Join-Path $Root "backend\run_geopilot_isolated_live_acquired_document_e2e_v1.py"

if (!(Test-Path $Py)) { throw "Acceptance Python file missing beside installer." }

Write-Host "============================================================"
Write-Host "GeoPilot Isolated Live Acquired-Document E2E Acceptance V1"
Write-Host "Temporary DB rows + file are cleaned after acceptance"
Write-Host "============================================================"

Write-Host "[1] Preflight services"
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "Service preflight failed." }

Write-Host "[2] Auto-ingestion regression gate"
docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Acquisition regression failed." }

Write-Host "[3] Stage acceptance script"
Copy-Item $Py $BackendPy -Force

try {
    Write-Host "[4] Execute isolated live E2E acceptance"
    docker compose exec -T backend python /app/run_geopilot_isolated_live_acquired_document_e2e_v1.py
    if ($LASTEXITCODE -ne 0) { throw "Isolated live acquired-document E2E acceptance failed." }
}
finally {
    Remove-Item $BackendPy -Force -ErrorAction SilentlyContinue
}

Write-Host "[5] Post-acceptance service health"
docker compose ps

Write-Host "============================================================"
Write-Host "ISOLATED LIVE ACQUIRED-DOCUMENT E2E V1 PASS"
Write-Host "============================================================"
Write-Host "Official GPP discovery: PASS"
Write-Host "Official PDF acquisition: PASS"
Write-Host "PlanningDocument/Version persistence: PASS"
Write-Host "source_kind=acquired: PASS"
Write-Host "Existing PDF ingestion/extraction: PASS"
Write-Host "Chunking: PASS"
Write-Host "Embedding index: PASS"
Write-Host "Document retrieval with citation provenance: PASS"
Write-Host "Temporary DB cleanup: PASS"
Write-Host "Temporary storage cleanup: PASS"
Write-Host "Existing project counts restored: PASS"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "RFN: FAIL-CLOSED"
Write-Host "============================================================"
