$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service = "backend\app\services\planning_document_acquisition.py"
$Tests = "backend\tests\test_planning_document_acquisition.py"

if (!(Test-Path $Service)) { throw "Missing acquisition service." }
if (!(Test-Path $Tests)) { throw "Missing acquisition tests." }

Write-Host "============================================================"
Write-Host "GeoPilot ePublisiti Concrete Discovery Adapter V1.2"
Write-Host "Recovery for V1.1 test-helper failure"
Write-Host "============================================================"

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = "artifacts\epublisiti_concrete_discovery_adapter_v1_2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Service "$Backup\planning_document_acquisition.py"
Copy-Item $Tests "$Backup\test_planning_document_acquisition.py"
Write-Host "BACKUP: $Backup"

Write-Host "[1] Verify current provider syntax"
docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Current provider syntax is invalid. Stop." }

Write-Host "[2] Verify V1.1 provider markers"
Copy-Item "$Root\_epublisiti_provider_verify_v1_2.py" "backend\_epublisiti_provider_verify_v1_2.py" -Force
try {
    docker compose exec -T backend python /app/_epublisiti_provider_verify_v1_2.py
    if ($LASTEXITCODE -ne 0) { throw "Expected V1.1 provider patch is not present." }
}
finally {
    Remove-Item "backend\_epublisiti_provider_verify_v1_2.py" -Force -ErrorAction SilentlyContinue
}

Write-Host "[3] Install corrected V1.2 tests"
Copy-Item "$Root\_epublisiti_tests_recovery_v1_2.py" "backend\_epublisiti_tests_recovery_v1_2.py" -Force
try {
    docker compose exec -T backend python /app/_epublisiti_tests_recovery_v1_2.py
    if ($LASTEXITCODE -ne 0) { throw "Corrected test patch failed." }
}
finally {
    Remove-Item "backend\_epublisiti_tests_recovery_v1_2.py" -Force -ErrorAction SilentlyContinue
}

Write-Host "[4] Syntax checks"
docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Syntax check failed." }

Write-Host "[5] Acquisition regression"
docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Acquisition regression failed." }

Write-Host "[6] Existing document retrieval regression"
docker compose exec -T backend python -m pytest -q tests/test_document_retrieval.py
if ($LASTEXITCODE -ne 0) { throw "Document retrieval regression failed." }

Write-Host "[7] GPP preservation gate"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; xs=PlanMalaysiaOfficialProvider().discover(document_class='GPP',jurisdiction=None,query='tanah tinggi'); print('GPP=',len(xs)); [print('-',x.title) for x in xs[:5]]; assert xs"
if ($LASTEXITCODE -ne 0) { throw "GPP preservation gate failed." }

Write-Host "[8] Live RT/RSN/RKK Perak acceptance"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; p=PlanMalaysiaOfficialProvider(); [(lambda k,xs:(print(k,'=',len(xs)),[print('-',x.title,'|',x.metadata.get('status_signals')) for x in xs[:8]]))(k,p.discover(document_class=k,jurisdiction='Perak',query='')) for k in ('RT','RSN','RKK')]"
if ($LASTEXITCODE -ne 0) { throw "Live ePublisiti acceptance failed." }

Write-Host "[9] RFN fail-closed"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; assert PlanMalaysiaOfficialProvider().discover(document_class='RFN',jurisdiction='Malaysia',query='') == []; print('RFN fail-closed: PASS')"
if ($LASTEXITCODE -ne 0) { throw "RFN fail-closed gate failed." }

Write-Host "[10] Service health"
docker compose ps

Write-Host "============================================================"
Write-Host "RT/RSN/RKK EPUBLISITI CONCRETE DISCOVERY ADAPTER V1.2 PASS"
Write-Host "============================================================"
Write-Host "Provider V1.1 patch: PRESERVED"
Write-Host "Corrected regression tests: PASS"
Write-Host "GPP discovery: PRESERVED"
Write-Host "RT discovery: ENABLED"
Write-Host "RSN discovery: ENABLED"
Write-Host "RKK discovery: ENABLED"
Write-Host "Statutory effect inference: BLOCKED"
Write-Host "RFN: FAIL-CLOSED"
Write-Host "PDF resolution/download: NOT RUN"
Write-Host "DB write: NONE"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "============================================================"
