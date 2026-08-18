$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service="$Root\backend\app\services\pdf_ingestion.py"
$Acq="$Root\backend\app\services\planning_document_acquisition.py"
$Tests="$Root\backend\tests\test_planning_document_acquisition.py"

$PatchHelper="$Root\patch_geopilot_acquired_pdf_ingestion_v1.py"
$WireHelper="$Root\wire_geopilot_acquired_pdf_ingestion_v1.py"
$FocusedTestHelper="$Root\test_geopilot_acquired_pdf_ingestion_v1.py"
$RepairHelper="$Root\repair_geopilot_auto_ingestion_regression_v1_3.py"

foreach($P in @($Service,$Acq,$Tests,$PatchHelper,$WireHelper,$FocusedTestHelper,$RepairHelper)){
  if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Acquired PDF Ingestion V1.3"
Write-Host "Robust target-test mock repair"
Write-Host "============================================================"

Write-Host "[1] Confirm V1.2 rollback restored production source"
$PdfText=Get-Content $Service -Raw
$AcqText=Get-Content $Acq -Raw
if($PdfText -match "def ingest_acquired_pdf\("){ throw "Unexpected acquired-PDF patch already present." }
if($AcqText -match "from app.services.pdf_ingestion import .*ingest_acquired_pdf"){ throw "Unexpected acquired-PDF wiring already present." }
Write-Host "Production rollback: CONFIRMED"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\acquired_pdf_ingestion_v1_3_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Service "$Backup\pdf_ingestion.py"
Copy-Item $Acq "$Backup\planning_document_acquisition.py"
Copy-Item $Tests "$Backup\test_planning_document_acquisition.py"
Write-Host "BACKUP: $Backup"

$Patch="$Root\backend\_acquired_pdf_patch_v1_3.py"
$Wire="$Root\backend\_acquired_pdf_wire_v1_3.py"
$Repair="$Root\backend\_auto_ingestion_regression_repair_v1_3.py"
$FocusedTest="$Root\backend\tests\test_acquired_pdf_ingestion_v1.py"

Copy-Item $PatchHelper $Patch -Force
Copy-Item $WireHelper $Wire -Force
Copy-Item $RepairHelper $Repair -Force
Copy-Item $FocusedTestHelper $FocusedTest -Force

try {
  Write-Host "[2] Apply separate acquired-PDF ingestion path"
  docker compose exec -T backend python /app/_acquired_pdf_patch_v1_3.py
  if($LASTEXITCODE -ne 0){ throw "PDF ingestion patch failed." }

  Write-Host "[3] Wire auto-acquisition pipeline"
  docker compose exec -T backend python /app/_acquired_pdf_wire_v1_3.py
  if($LASTEXITCODE -ne 0){ throw "Wiring failed." }

  Write-Host "[4] Repair target regression mock"
  docker compose exec -T backend python /app/_auto_ingestion_regression_repair_v1_3.py
  if($LASTEXITCODE -ne 0){ throw "Regression repair failed." }

  Write-Host "[5] Verify target test now mocks acquired path"
  docker compose exec -T backend python -c "from pathlib import Path; t=Path('/app/tests/test_planning_document_acquisition.py').read_text(); s=t.index('def test_auto_ingestion_v1_1_pipeline_calls_existing_layers('); e=t.find('\ndef ',s+1); b=t[s:] if e<0 else t[s:e]; assert 'mod, \"ingest_acquired_pdf\",' in b; assert 'mod, \"ingest_registered_pdf\",' not in b; print('target_mock=PASS')"
  if($LASTEXITCODE -ne 0){ throw "Target regression mock verification failed." }

  Write-Host "[6] Syntax checks"
  docker compose exec -T backend python -m py_compile /app/app/services/pdf_ingestion.py /app/app/services/planning_document_acquisition.py /app/tests/test_planning_document_acquisition.py /app/tests/test_acquired_pdf_ingestion_v1.py
  if($LASTEXITCODE -ne 0){ throw "Syntax check failed." }

  Write-Host "[7] Focused acquired-PDF tests"
  docker compose exec -T backend python -m pytest -q tests/test_acquired_pdf_ingestion_v1.py
  if($LASTEXITCODE -ne 0){ throw "Focused acquired-PDF tests failed." }

  Write-Host "[8] Acquisition regression"
  docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
  if($LASTEXITCODE -ne 0){ throw "Acquisition regression failed." }

  Write-Host "[9] Existing PDF ingestion regression"
  docker compose exec -T backend python -m pytest -q tests/test_pdf_ingestion.py
  if($LASTEXITCODE -ne 0){ throw "PDF ingestion regression failed." }

  Write-Host "[10] Wiring verification"
  docker compose exec -T backend python -c "import inspect; from app.services.pdf_ingestion import ingest_registered_pdf,ingest_acquired_pdf; from app.services.planning_document_acquisition import ingest_acquired_document; assert 'version.source_kind != \"upload\"' in inspect.getsource(ingest_registered_pdf); assert 'version.source_kind != \"acquired\"' in inspect.getsource(ingest_acquired_pdf); assert 'ingest_acquired_pdf(' in inspect.getsource(ingest_acquired_document); print('manual_guard=PASS'); print('acquired_guard=PASS'); print('auto_wiring=PASS')"
  if($LASTEXITCODE -ne 0){ throw "Wiring verification failed." }

  Write-Host "[11] Service health"
  docker compose ps

  Write-Host "============================================================"
  Write-Host "ACQUIRED PDF INGESTION V1.3 PASS"
  Write-Host "============================================================"
  Write-Host "Production rollback verification: PASS"
  Write-Host "Manual upload guard: PRESERVED"
  Write-Host "Acquired source guard: ENABLED"
  Write-Host "Target regression mock: FIXED"
  Write-Host "Acquisition regression: PASS"
  Write-Host "PDF ingestion regression: PASS"
  Write-Host "Migration: NONE"
  Write-Host "Frontend change: NONE"
  Write-Host "Live E2E rerun: NEXT GATE"
  Write-Host "============================================================"
}
catch {
  Write-Host "INSTALL FAILED - restoring production source and test."
  Copy-Item "$Backup\pdf_ingestion.py" $Service -Force
  Copy-Item "$Backup\planning_document_acquisition.py" $Acq -Force
  Copy-Item "$Backup\test_planning_document_acquisition.py" $Tests -Force
  throw
}
finally {
  Remove-Item $Patch,$Wire,$Repair -Force -ErrorAction SilentlyContinue
}
