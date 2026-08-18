$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Py = Join-Path $Root "run_geopilot_isolated_live_acquired_document_e2e_v1_1.py"
$BackendPy = Join-Path $Root "backend\run_geopilot_isolated_live_acquired_document_e2e_v1_1.py"
if (!(Test-Path $Py)) { throw "Acceptance Python V1.1 file missing." }

Write-Host "============================================================"
Write-Host "GeoPilot Isolated Live Acquired-Document E2E Acceptance V1.1"
Write-Host "Recovery for incorrect SessionLocal import"
Write-Host "============================================================"

Write-Host "[1] DB session factory verification"
docker compose exec -T backend python -c "from app.db import get_session_factory; s=get_session_factory()(); print('session_factory=PASS'); s.close()"
if ($LASTEXITCODE -ne 0) { throw "DB session factory verification failed." }

Write-Host "[2] Regression gate"
docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Acquisition regression failed." }

Write-Host "[3] Stage corrected acceptance"
Copy-Item $Py $BackendPy -Force

try {
    Write-Host "[4] Execute isolated live E2E V1.1"
    docker compose exec -T backend python /app/run_geopilot_isolated_live_acquired_document_e2e_v1_1.py
    if ($LASTEXITCODE -ne 0) { throw "Isolated live acquired-document E2E V1.1 failed." }
}
finally {
    Remove-Item $BackendPy -Force -ErrorAction SilentlyContinue
}

Write-Host "[5] Service health"
docker compose ps

Write-Host "============================================================"
Write-Host "ISOLATED LIVE ACQUIRED-DOCUMENT E2E V1.1 PASS"
Write-Host "============================================================"
Write-Host "DB session factory: PASS"
Write-Host "Official GPP discovery/acquisition: PASS"
Write-Host "PlanningDocument/Version persistence: PASS"
Write-Host "source_kind=acquired: PASS"
Write-Host "PDF ingestion/extraction: PASS"
Write-Host "Chunking: PASS"
Write-Host "Embedding index: PASS"
Write-Host "Scoped retrieval: PASS"
Write-Host "Temporary DB cleanup: PASS"
Write-Host "Temporary storage cleanup: PASS"
Write-Host "Project counts restored: PASS"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "============================================================"
