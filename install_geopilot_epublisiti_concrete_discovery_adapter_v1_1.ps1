$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service="backend\app\services\planning_document_acquisition.py"
$Tests="backend\tests\test_planning_document_acquisition.py"
$FailedBackup="artifacts\epublisiti_concrete_discovery_adapter_v1_backup_20260816_181009"
if (!(Test-Path $Service)) { throw "Missing acquisition service." }
if (!(Test-Path $Tests)) { throw "Missing acquisition tests." }
if (!(Test-Path "$FailedBackup\planning_document_acquisition.py")) { throw "Expected V1 backup not found." }

Write-Host "============================================================"
Write-Host "GeoPilot ePublisiti Concrete Discovery Adapter V1.1"
Write-Host "Safe recovery from V1 patch failure"
Write-Host "============================================================"

Write-Host "[1] Failed-V1 integrity gate"
$CurrentHash=(Get-FileHash $Service -Algorithm SHA256).Hash
$BackupHash=(Get-FileHash "$FailedBackup\planning_document_acquisition.py" -Algorithm SHA256).Hash
Write-Host "current_sha256=$CurrentHash"
Write-Host "v1_backup_sha256=$BackupHash"
if ($CurrentHash -eq $BackupHash) {
  Write-Host "Failed V1 production partial modification: NONE"
} else {
  Write-Host "Current differs from pre-V1 backup; inspect known adapter markers."
  $Current=Get-Content $Service -Raw
  if ($Current -match "EPUBLISITI_HOME_URL|_extract_epublisiti|STATE_SLUGS") {
    Write-Host "Partial V1 markers detected. Restoring exact pre-V1 service backup."
    Copy-Item "$FailedBackup\planning_document_acquisition.py" $Service -Force
  } else {
    throw "BLOCKED: current service differs from backup for an unknown reason. No automatic restore performed."
  }
}

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="artifacts\epublisiti_concrete_discovery_adapter_v1_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Service "$Backup\planning_document_acquisition.py"
Copy-Item $Tests "$Backup\test_planning_document_acquisition.py"
Write-Host "V1.1 BACKUP: $Backup"

Write-Host "[2] Stage temporary patch files inside backend bind mount"
Copy-Item "$Root\_epub_patch.py" "backend\_epub_patch_v1_1.py" -Force
Copy-Item "$Root\_epub_tests.py" "backend\_epub_tests_v1_1.py" -Force

try {
  Write-Host "[3] Apply provider patch"
  docker compose exec -T backend python /app/_epub_patch_v1_1.py
  if ($LASTEXITCODE -ne 0) { throw "Provider patch failed." }

  Write-Host "[4] Apply regression tests"
  docker compose exec -T backend python /app/_epub_tests_v1_1.py
  if ($LASTEXITCODE -ne 0) { throw "Test patch failed." }
}
finally {
  Remove-Item "backend\_epub_patch_v1_1.py" -Force -ErrorAction SilentlyContinue
  Remove-Item "backend\_epub_tests_v1_1.py" -Force -ErrorAction SilentlyContinue
}

Write-Host "[5] Syntax checks"
docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Syntax failed." }

Write-Host "[6] Full acquisition regression"
docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Acquisition regression failed." }

Write-Host "[7] Existing document retrieval regression"
docker compose exec -T backend python -m pytest -q tests/test_document_retrieval.py
if ($LASTEXITCODE -ne 0) { throw "Retrieval regression failed." }

Write-Host "[8] GPP live preservation gate"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; xs=PlanMalaysiaOfficialProvider().discover(document_class='GPP',jurisdiction=None,query='tanah tinggi'); print('GPP tanah tinggi=',len(xs)); [print('-',x.title) for x in xs[:5]]; assert xs"
if ($LASTEXITCODE -ne 0) { throw "GPP preservation gate failed." }

Write-Host "[9] RT/RSN/RKK live read-only Perak acceptance"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; p=PlanMalaysiaOfficialProvider(); [(lambda k,xs:(print(k,'=',len(xs)),[print('-',x.title,'| status=',x.metadata.get('document_status'),'| signals=',x.metadata.get('status_signals')) for x in xs[:8]]))(k,p.discover(document_class=k,jurisdiction='Perak',query='')) for k in ('RT','RSN','RKK')]"
if ($LASTEXITCODE -ne 0) { throw "Live ePublisiti acceptance failed." }

Write-Host "[10] RFN fail-closed gate"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; assert PlanMalaysiaOfficialProvider().discover(document_class='RFN',jurisdiction='Malaysia',query='') == []; print('RFN fail-closed: PASS')"
if ($LASTEXITCODE -ne 0) { throw "RFN fail-closed gate failed." }

Write-Host "[11] Service health"
docker compose ps

Write-Host "============================================================"
Write-Host "RT/RSN/RKK EPUBLISITI CONCRETE DISCOVERY ADAPTER V1.1 PASS"
Write-Host "============================================================"
Write-Host "Failed V1 recovery: PASS"
Write-Host "GPP discovery: PRESERVED"
Write-Host "RT discovery: ENABLED"
Write-Host "RSN discovery: ENABLED"
Write-Host "RKK discovery: ENABLED"
Write-Host "Document status: UNVERIFIED unless separately proven"
Write-Host "Statutory-effect fabrication: BLOCKED"
Write-Host "RFN: FAIL-CLOSED"
Write-Host "PDF resolution/download: NOT RUN"
Write-Host "DB write: NONE"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "============================================================"
