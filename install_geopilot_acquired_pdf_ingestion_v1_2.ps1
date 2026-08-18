$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service="$Root\backend\app\services\pdf_ingestion.py"
$Acq="$Root\backend\app\services\planning_document_acquisition.py"
$AcqTests="$Root\backend\tests\test_planning_document_acquisition.py"
$PatchHelper="$Root\patch_geopilot_acquired_pdf_ingestion_v1.py"
$WireHelper="$Root\wire_geopilot_acquired_pdf_ingestion_v1.py"
$FocusedTestHelper="$Root\test_geopilot_acquired_pdf_ingestion_v1.py"
$RegressionRepairHelper="$Root\repair_geopilot_auto_ingestion_regression_v1_2.py"

foreach($P in @($Service,$Acq,$AcqTests,$PatchHelper,$WireHelper,$FocusedTestHelper,$RegressionRepairHelper)){
  if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Acquired PDF Ingestion V1.2"
Write-Host "Recovery for stale auto-ingestion regression mock"
Write-Host "============================================================"

Write-Host "[1] Confirm V1.1 rollback restored production source"
$PdfText=Get-Content $Service -Raw
$AcqText=Get-Content $Acq -Raw
if($PdfText -match "def ingest_acquired_pdf\("){
  throw "Unexpected acquired-PDF patch already present. Stop for inspection."
}
if($AcqText -match "from app.services.pdf_ingestion import .*ingest_acquired_pdf"){
  throw "Unexpected acquired-PDF wiring already present. Stop for inspection."
}
Write-Host "Production rollback: CONFIRMED"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\acquired_pdf_ingestion_v1_2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Service "$Backup\pdf_ingestion.py"
Copy-Item $Acq "$Backup\planning_document_acquisition.py"
Copy-Item $AcqTests "$Backup\test_planning_document_acquisition.py"
Write-Host "BACKUP: $Backup"

$Patch="$Root\backend\_acquired_pdf_patch_v1_2.py"
$Wire="$Root\backend\_acquired_pdf_wire_v1_2.py"
$Repair="$Root\backend\_auto_ingestion_regression_repair_v1_2.py"
$FocusedTest="$Root\backend\tests\test_acquired_pdf_ingestion_v1.py"

Copy-Item $PatchHelper $Patch -Force
Copy-Item $WireHelper $Wire -Force
Copy-Item $RegressionRepairHelper $Repair -Force
Copy-Item $FocusedTestHelper $FocusedTest -Force

try {
  Write-Host "[2] Apply separate acquired-PDF ingestion path"
  docker compose exec -T backend python /app/_acquired_pdf_patch_v1_2.py
  if($LASTEXITCODE -ne 0){ throw "PDF ingestion patch failed." }

  Write-Host "[3] Wire auto-acquisition pipeline to acquired path"
  docker compose exec -T backend python /app/_acquired_pdf_wire_v1_2.py
  if($LASTEXITCODE -ne 0){ throw "Auto-ingestion wiring failed." }

  Write-Host "[4] Repair stale regression mock only"
  docker compose exec -T backend python /app/_auto_ingestion_regression_repair_v1_2.py
  if($LASTEXITCODE -ne 0){ throw "Regression test repair failed." }

  Write-Host "[5] Syntax checks"
  docker compose exec -T backend python -m py_compile /app/app/services/pdf_ingestion.py /app/app/services/planning_document_acquisition.py /app/tests/test_planning_document_acquisition.py /app/tests/test_acquired_pdf_ingestion_v1.py
  if($LASTEXITCODE -ne 0){ throw "Syntax check failed." }

  Write-Host "[6] Focused acquired-PDF safety tests"
  docker compose exec -T backend python -m pytest -q tests/test_acquired_pdf_ingestion_v1.py
  if($LASTEXITCODE -ne 0){ throw "Focused acquired-PDF tests failed." }

  Write-Host "[7] Acquisition regression"
  docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
  if($LASTEXITCODE -ne 0){ throw "Acquisition regression failed." }

  Write-Host "[8] Existing PDF ingestion regression"
  docker compose exec -T backend python -m pytest -q tests/test_pdf_ingestion.py
  if($LASTEXITCODE -ne 0){ throw "PDF ingestion regression failed." }

  Write-Host "[9] Wiring verification"
  docker compose exec -T backend python -c "import inspect; from app.services.pdf_ingestion import ingest_registered_pdf,ingest_acquired_pdf; from app.services.planning_document_acquisition import ingest_acquired_document; assert 'version.source_kind != \"upload\"' in inspect.getsource(ingest_registered_pdf); assert 'version.source_kind != \"acquired\"' in inspect.getsource(ingest_acquired_pdf); assert 'ingest_acquired_pdf(' in inspect.getsource(ingest_acquired_document); print('manual_guard=PASS'); print('acquired_guard=PASS'); print('auto_wiring=PASS')"
  if($LASTEXITCODE -ne 0){ throw "Wiring verification failed." }

  Write-Host "[10] Service health"
  docker compose ps

  Write-Host "============================================================"
  Write-Host "ACQUIRED PDF INGESTION V1.2 PASS"
  Write-Host "============================================================"
  Write-Host "Production rollback verification: PASS"
  Write-Host "Manual upload guard: PRESERVED"
  Write-Host "Acquired source guard: ENABLED"
  Write-Host "Auto-ingestion call path: ingest_acquired_pdf"
  Write-Host "Stale regression mock: FIXED"
  Write-Host "Existing extraction/storage logic: REUSED"
  Write-Host "Regression suite: PASS"
  Write-Host "Migration: NONE"
  Write-Host "Frontend change: NONE"
  Write-Host "Live E2E rerun: NEXT GATE"
  Write-Host "============================================================"
}
catch {
  Write-Host "INSTALL FAILED - restoring production source and repaired test."
  Copy-Item "$Backup\pdf_ingestion.py" $Service -Force
  Copy-Item "$Backup\planning_document_acquisition.py" $Acq -Force
  Copy-Item "$Backup\test_planning_document_acquisition.py" $AcqTests -Force
  throw
}
finally {
  Remove-Item $Patch,$Wire,$Repair -Force -ErrorAction SilentlyContinue
}
