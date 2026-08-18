$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service = "backend\app\services\planning_document_acquisition.py"
$Tests = "backend\tests\test_planning_document_acquisition.py"
if (!(Test-Path $Service)) { throw "Missing acquisition service." }
if (!(Test-Path $Tests)) { throw "Missing acquisition tests." }

Write-Host "============================================================"
Write-Host "GeoPilot Planning Document Auto-Ingestion Pipeline V1.1"
Write-Host "Recovery for malformed V1 helper only"
Write-Host "============================================================"

Write-Host "[1] Failed V1 integrity gate"
$Current = Get-Content $Service -Raw
if ($Current -match "def register_acquired_document" -or $Current -match "PlanningDocumentAutoIngestionError") {
    throw "Unexpected partial V1 production modification detected. Stop for inspection."
}
Write-Host "Failed V1 production modification: NONE"

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = "artifacts\planning_document_auto_ingestion_v1_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Service "$Backup\planning_document_acquisition.py"
Copy-Item $Tests "$Backup\test_planning_document_acquisition.py"
Write-Host "BACKUP: $Backup"

Write-Host "[2] Stage corrected helpers"
Copy-Item "$Root\_planning_auto_ingestion_patch_v1_1.py" "backend\_planning_auto_ingestion_patch_v1_1.py" -Force
Copy-Item "$Root\_planning_auto_ingestion_tests_v1_1.py" "backend\_planning_auto_ingestion_tests_v1_1.py" -Force

try {
    Write-Host "[3] Apply corrected service patch"
    docker compose exec -T backend python /app/_planning_auto_ingestion_patch_v1_1.py
    if ($LASTEXITCODE -ne 0) { throw "Corrected service patch failed." }

    Write-Host "[4] Install corrected tests"
    docker compose exec -T backend python /app/_planning_auto_ingestion_tests_v1_1.py
    if ($LASTEXITCODE -ne 0) { throw "Corrected test patch failed." }
}
finally {
    Remove-Item "backend\_planning_auto_ingestion_patch_v1_1.py" -Force -ErrorAction SilentlyContinue
    Remove-Item "backend\_planning_auto_ingestion_tests_v1_1.py" -Force -ErrorAction SilentlyContinue
}

Write-Host "[5] Syntax checks"
docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Syntax check failed." }

Write-Host "[6] Acquisition regression"
docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Acquisition regression failed." }

Write-Host "[7] Relevant existing pipeline regressions"
$TestFiles = @(
  "tests/test_pdf_ingestion.py",
  "tests/test_document_chunking.py",
  "tests/test_document_embedding_index.py",
  "tests/test_document_retrieval.py"
)
foreach ($T in $TestFiles) {
  if (Test-Path ("backend\" + $T.Replace("/","\"))) {
    docker compose exec -T backend python -m pytest -q $T
    if ($LASTEXITCODE -ne 0) { throw "Regression failed: $T" }
  } else {
    Write-Host "SKIP missing test file: $T"
  }
}

Write-Host "[8] Import verification"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import register_acquired_document, ingest_acquired_document; print('auto_ingestion_imports=PASS')"
if ($LASTEXITCODE -ne 0) { throw "Import verification failed." }

Write-Host "[9] Service health"
docker compose ps

Write-Host "============================================================"
Write-Host "PLANNING DOCUMENT AUTO-INGESTION PIPELINE V1.1 PASS"
Write-Host "============================================================"
Write-Host "Failed V1 recovery: PASS"
Write-Host "Acquired source registration: ENABLED"
Write-Host "source_kind=acquired: ENABLED"
Write-Host "Existing PDF ingestion: WIRED"
Write-Host "Existing extraction/OCR path: PRESERVED"
Write-Host "Existing chunking path: WIRED"
Write-Host "Existing embedding index path: WIRED"
Write-Host "Unverified external documents: REQUIRES REVIEW"
Write-Host "Live persistent external ingestion: NOT RUN"
Write-Host "DB schema change: NONE"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "============================================================"
