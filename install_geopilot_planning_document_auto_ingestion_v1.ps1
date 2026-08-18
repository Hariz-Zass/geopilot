$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service = "backend\app\services\planning_document_acquisition.py"
$Tests = "backend\tests\test_planning_document_acquisition.py"
if (!(Test-Path $Service)) { throw "Missing acquisition service." }
if (!(Test-Path $Tests)) { throw "Missing acquisition tests." }

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = "artifacts\planning_document_auto_ingestion_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Service "$Backup\planning_document_acquisition.py"
Copy-Item $Tests "$Backup\test_planning_document_acquisition.py"

Write-Host "============================================================"
Write-Host "GeoPilot Planning Document Auto-Ingestion Pipeline V1"
Write-Host "Provider-ready registration -> existing PDF/OCR/chunk/index"
Write-Host "NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"

Write-Host "[1] Stage helpers"
Copy-Item "$Root\_planning_auto_ingestion_patch_v1.py" "backend\_planning_auto_ingestion_patch_v1.py" -Force
Copy-Item "$Root\_planning_auto_ingestion_tests_v1.py" "backend\_planning_auto_ingestion_tests_v1.py" -Force

try {
    Write-Host "[2] Apply auto-ingestion service patch"
    docker compose exec -T backend python /app/_planning_auto_ingestion_patch_v1.py
    if ($LASTEXITCODE -ne 0) { throw "Auto-ingestion patch failed." }

    Write-Host "[3] Install regression tests"
    docker compose exec -T backend python /app/_planning_auto_ingestion_tests_v1.py
    if ($LASTEXITCODE -ne 0) { throw "Auto-ingestion test patch failed." }
}
finally {
    Remove-Item "backend\_planning_auto_ingestion_patch_v1.py" -Force -ErrorAction SilentlyContinue
    Remove-Item "backend\_planning_auto_ingestion_tests_v1.py" -Force -ErrorAction SilentlyContinue
}

Write-Host "[4] Syntax checks"
docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Syntax check failed." }

Write-Host "[5] Acquisition regression"
docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Acquisition regression failed." }

Write-Host "[6] PDF ingestion regression"
docker compose exec -T backend python -m pytest -q tests/test_pdf_ingestion.py
if ($LASTEXITCODE -ne 0) { throw "PDF ingestion regression failed." }

Write-Host "[7] Chunking regression"
docker compose exec -T backend python -m pytest -q tests/test_document_chunking.py
if ($LASTEXITCODE -ne 0) { throw "Chunking regression failed." }

Write-Host "[8] Embedding index regression"
docker compose exec -T backend python -m pytest -q tests/test_document_embedding_index.py
if ($LASTEXITCODE -ne 0) { throw "Embedding index regression failed." }

Write-Host "[9] Retrieval regression"
docker compose exec -T backend python -m pytest -q tests/test_document_retrieval.py
if ($LASTEXITCODE -ne 0) { throw "Retrieval regression failed." }

Write-Host "[10] Import verification"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import register_acquired_document, ingest_acquired_document; print('register_acquired_document: OK'); print('ingest_acquired_document: OK')"
if ($LASTEXITCODE -ne 0) { throw "Import verification failed." }

Write-Host "[11] Service health"
docker compose ps

Write-Host "============================================================"
Write-Host "PLANNING DOCUMENT AUTO-INGESTION PIPELINE V1 PASS"
Write-Host "============================================================"
Write-Host "Acquired source registration: ENABLED"
Write-Host "source_kind=acquired: ENABLED"
Write-Host "Official source/provenance persistence: ENABLED"
Write-Host "Existing immutable PDF ingestion: WIRED"
Write-Host "Existing extraction/OCR path: PRESERVED"
Write-Host "Existing chunking path: WIRED"
Write-Host "Existing embedding index path: WIRED"
Write-Host "Unverified statutory status -> requires_review: ENABLED"
Write-Host "Arbitrary fabrication: BLOCKED"
Write-Host "Live persistent external document ingestion: NOT RUN"
Write-Host "DB schema change: NONE"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "RFN: FAIL-CLOSED"
Write-Host "============================================================"
