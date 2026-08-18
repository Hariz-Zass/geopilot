$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service="$Root\backend\app\services\pdf_ingestion.py"
$Acq="$Root\backend\app\services\planning_document_acquisition.py"
$PatchHelper="$Root\patch_geopilot_acquired_pdf_ingestion_v1.py"
$WireHelper="$Root\wire_geopilot_acquired_pdf_ingestion_v1.py"
$TestHelper="$Root\test_geopilot_acquired_pdf_ingestion_v1.py"

foreach($P in @($Service,$Acq,$PatchHelper,$WireHelper,$TestHelper)){
  if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Acquired PDF Ingestion V1.1"
Write-Host "Recovery for pytest executable import-path issue"
Write-Host "============================================================"

Write-Host "[1] Confirm production source was restored after failed V1"
$PdfText=Get-Content $Service -Raw
$AcqText=Get-Content $Acq -Raw
if($PdfText -match "def ingest_acquired_pdf\("){
  throw "Unexpected acquired-PDF patch already present. Stop for inspection."
}
if($AcqText -match "from app.services.pdf_ingestion import .*ingest_acquired_pdf"){
  throw "Unexpected acquired-PDF wiring already present. Stop for inspection."
}
Write-Host "Failed V1 production rollback: CONFIRMED"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\acquired_pdf_ingestion_v1_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Service "$Backup\pdf_ingestion.py"
Copy-Item $Acq "$Backup\planning_document_acquisition.py"
Write-Host "BACKUP: $Backup"

$Patch="$Root\backend\_acquired_pdf_patch_v1_1.py"
$Wire="$Root\backend\_acquired_pdf_wire_v1_1.py"
$Test="$Root\backend\tests\test_acquired_pdf_ingestion_v1.py"

Copy-Item $PatchHelper $Patch -Force
Copy-Item $WireHelper $Wire -Force
Copy-Item $TestHelper $Test -Force

try {
  Write-Host "[2] Apply separate acquired-PDF ingestion path"
  docker compose exec -T backend python /app/_acquired_pdf_patch_v1_1.py
  if($LASTEXITCODE -ne 0){ throw "PDF ingestion patch failed." }

  Write-Host "[3] Wire auto-acquisition pipeline"
  docker compose exec -T backend python /app/_acquired_pdf_wire_v1_1.py
  if($LASTEXITCODE -ne 0){ throw "Auto-ingestion wiring failed." }

  Write-Host "[4] Syntax checks"
  docker compose exec -T backend python -m py_compile /app/app/services/pdf_ingestion.py /app/app/services/planning_document_acquisition.py /app/tests/test_acquired_pdf_ingestion_v1.py
  if($LASTEXITCODE -ne 0){ throw "Syntax check failed." }

  Write-Host "[5] Focused acquired-PDF safety tests via python -m pytest"
  docker compose exec -T backend python -m pytest -q tests/test_acquired_pdf_ingestion_v1.py
  if($LASTEXITCODE -ne 0){ throw "Focused acquired-PDF tests failed." }

  Write-Host "[6] Existing acquisition regression"
  docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
  if($LASTEXITCODE -ne 0){ throw "Acquisition regression failed." }

  Write-Host "[7] Existing PDF ingestion regression"
  docker compose exec -T backend python -m pytest -q tests/test_pdf_ingestion.py
  if($LASTEXITCODE -ne 0){ throw "PDF ingestion regression failed." }

  Write-Host "[8] Import/wiring verification"
  docker compose exec -T backend python -c "from app.services.pdf_ingestion import ingest_acquired_pdf,ingest_registered_pdf; import inspect; from app.services.planning_document_acquisition import ingest_acquired_document; s=inspect.getsource(ingest_acquired_document); assert 'ingest_acquired_pdf(' in s; assert 'version.source_kind != \"upload\"' in inspect.getsource(ingest_registered_pdf); print('manual_guard=PASS'); print('acquired_path=PASS'); print('auto_wiring=PASS')"
  if($LASTEXITCODE -ne 0){ throw "Import/wiring verification failed." }

  Write-Host "[9] Service health"
  docker compose ps

  Write-Host "============================================================"
  Write-Host "ACQUIRED PDF INGESTION V1.1 PASS"
  Write-Host "============================================================"
  Write-Host "V1 rollback verification: PASS"
  Write-Host "Manual upload guard: PRESERVED"
  Write-Host "Acquired source guard: ENABLED"
  Write-Host "Checksum/file-size validation: PRESERVED"
  Write-Host "Existing extraction/page persistence: REUSED"
  Write-Host "Existing immutable storage path: REUSED"
  Write-Host "Auto-acquisition pipeline wiring: ENABLED"
  Write-Host "Regression suite: PASS"
  Write-Host "Migration: NONE"
  Write-Host "Frontend change: NONE"
  Write-Host "Live E2E rerun: NEXT GATE"
  Write-Host "============================================================"
}
catch {
  Write-Host "INSTALL FAILED - restoring production source."
  Copy-Item "$Backup\pdf_ingestion.py" $Service -Force
  Copy-Item "$Backup\planning_document_acquisition.py" $Acq -Force
  throw
}
finally {
  Remove-Item $Patch,$Wire -Force -ErrorAction SilentlyContinue
}
