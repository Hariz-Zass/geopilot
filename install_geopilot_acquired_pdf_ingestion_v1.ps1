$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Service="$Root\backend\app\services\pdf_ingestion.py"
$Acq="$Root\backend\app\services\planning_document_acquisition.py"
$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\acquired_pdf_ingestion_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Service "$Backup\pdf_ingestion.py"; Copy-Item $Acq "$Backup\planning_document_acquisition.py"
Write-Host "BACKUP: $Backup"
Copy-Item "$Root\patch_geopilot_acquired_pdf_ingestion_v1.py" "$Root\backend\_acquired_pdf_patch_v1.py" -Force
Copy-Item "$Root\wire_geopilot_acquired_pdf_ingestion_v1.py" "$Root\backend\_acquired_pdf_wire_v1.py" -Force
Copy-Item "$Root\test_geopilot_acquired_pdf_ingestion_v1.py" "$Root\backend\tests\test_acquired_pdf_ingestion_v1.py" -Force
try {
 Write-Host "[1] Apply separate acquired-PDF ingestion path"
 docker compose exec -T backend python /app/_acquired_pdf_patch_v1.py
 if($LASTEXITCODE-ne 0){throw "PDF ingestion patch failed."}
 Write-Host "[2] Wire auto-acquisition pipeline"
 docker compose exec -T backend python /app/_acquired_pdf_wire_v1.py
 if($LASTEXITCODE-ne 0){throw "Wiring failed."}
 Write-Host "[3] Syntax"; docker compose exec -T backend python -m py_compile /app/app/services/pdf_ingestion.py /app/app/services/planning_document_acquisition.py
 if($LASTEXITCODE-ne 0){throw "Syntax failed."}
 Write-Host "[4] Focused safety tests"; docker compose exec -T backend pytest -q tests/test_acquired_pdf_ingestion_v1.py
 if($LASTEXITCODE-ne 0){throw "Focused tests failed."}
 Write-Host "[5] Acquisition regression"; docker compose exec -T backend pytest -q tests/test_planning_document_acquisition.py
 if($LASTEXITCODE-ne 0){throw "Acquisition regression failed."}
 Write-Host "[6] PDF regression"; docker compose exec -T backend pytest -q tests/test_pdf_ingestion.py
 if($LASTEXITCODE-ne 0){throw "PDF regression failed."}
 Write-Host "============================================================"
 Write-Host "ACQUIRED PDF INGESTION V1 PASS"
 Write-Host "Manual upload guard: PRESERVED"
 Write-Host "Acquired source guard: ENABLED"
 Write-Host "Existing extraction/storage: REUSED"
 Write-Host "Migration: NONE"
 Write-Host "Frontend change: NONE"
 Write-Host "Live E2E rerun: NEXT GATE"
 Write-Host "============================================================"
} catch {
 Write-Host "INSTALL FAILED - restoring production source."
 Copy-Item "$Backup\pdf_ingestion.py" $Service -Force; Copy-Item "$Backup\planning_document_acquisition.py" $Acq -Force
 throw
} finally {
 Remove-Item "$Root\backend\_acquired_pdf_patch_v1.py","$Root\backend\_acquired_pdf_wire_v1.py" -Force -ErrorAction SilentlyContinue
}
