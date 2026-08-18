$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service="backend\app\services\planning_document_acquisition.py"
$Tests="backend\tests\test_planning_document_acquisition.py"
if (!(Test-Path $Service)) { throw "Missing acquisition service." }
if (!(Test-Path $Tests)) { throw "Missing acquisition tests." }

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="artifacts\epublisiti_concrete_discovery_adapter_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Service "$Backup\planning_document_acquisition.py"
Copy-Item $Tests "$Backup\test_planning_document_acquisition.py"

Write-Host "============================================================"
Write-Host "GeoPilot RT/RSN/RKK ePublisiti Concrete Discovery Adapter V1"
Write-Host "NO DB WRITE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"

Write-Host "[1] Patch provider"
"ZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCgpwID0gUGF0aCgiL2FwcC9hcHAvc2VydmljZXMvcGxhbm5pbmdfZG9jdW1lbnRfYWNxdWlzaXRpb24ucHkiKQpzID0gcC5yZWFkX3RleHQoZW5jb2Rpbmc9InV0Zi04LXNpZyIpCgojIFdlIGV4cGVjdCBHUFAgVjEgYWxyZWFkeSBpbnN0YWxsZWQuCmlmICJjbGFzcyBQbGFuTWFsYXlzaWFPZmZpY2lhbFByb3ZpZGVyOiIgbm90IGluIHM6CiAgICByYWlzZSBTeXN0ZW1FeGl0KCJCTE9DS0VEOiBQbGFuTWFsYXlzaWFPZmZpY2lhbFByb3ZpZGVyIG5vdCBmb3VuZC4iKQoKc3RhcnQgPSBzLmluZGV4KCJjbGFzcyBQbGFuTWFsYXlzaWFPZmZpY2lhbFByb3ZpZGVyOiIpCnByZWZpeCA9IHNbOnN0YXJ0XQoKcHJvdmlkZXIgPSBy" | docker compose exec -T backend python -c "import sys,base64; exec(base64.b64decode(sys.stdin.read()).decode())"
if ($LASTEXITCODE -ne 0) { throw "Provider patch failed." }

Write-Host "[2] Patch tests"
"ZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCgpwID0gUGF0aCgiL2FwcC90ZXN0cy90ZXN0X3BsYW5uaW5nX2RvY3VtZW50X2FjcXVpc2l0aW9uLnB5IikKcyA9IHAucmVhZF90ZXh0KGVuY29kaW5nPSJ1dGYtOC1zaWciKQoKZXh0cmEgPSBy" | docker compose exec -T backend python -c "import sys,base64; exec(base64.b64decode(sys.stdin.read()).decode())"
if ($LASTEXITCODE -ne 0) { throw "Test patch failed." }

Write-Host "[3] Syntax checks"
docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Syntax check failed." }

Write-Host "[4] Acquisition regression"
docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Acquisition regression failed." }

Write-Host "[5] Existing retrieval regression"
docker compose exec -T backend python -m pytest -q tests/test_document_retrieval.py
if ($LASTEXITCODE -ne 0) { throw "Document retrieval regression failed." }

Write-Host "[6] LIVE READ-ONLY Perak discovery"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; p=PlanMalaysiaOfficialProvider(); [(lambda k,xs:(print(k,'=',len(xs)),[print(' -',x.title,'|',x.metadata.get('status_signals')) for x in xs[:10]]))(k,p.discover(document_class=k,jurisdiction='Perak',query='')) for k in ['RT','RSN','RKK']]"
if ($LASTEXITCODE -ne 0) { throw "Live Perak discovery failed." }

Write-Host "[7] LIVE READ-ONLY cross-jurisdiction smoke"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; p=PlanMalaysiaOfficialProvider(); tests=[('RT','Pahang','Temerloh'),('RSN','Terengganu',''),('RKK','Pahang','Tasik Chini')]; [(lambda k,j,q,xs:print(k,j,q,'=>',len(xs)))(k,j,q,p.discover(document_class=k,jurisdiction=j,query=q)) for k,j,q in tests]"
if ($LASTEXITCODE -ne 0) { throw "Cross-jurisdiction discovery failed." }

Write-Host "[8] Health"
docker compose ps

Write-Host "============================================================"
Write-Host "RT/RSN/RKK EPUBLISITI CONCRETE DISCOVERY ADAPTER V1 PASS"
Write-Host "============================================================"
Write-Host "RT discovery: ENABLED"
Write-Host "RSN discovery: ENABLED"
Write-Host "RKK discovery: ENABLED"
Write-Host "Jurisdiction filtering: ENABLED"
Write-Host "Draft/replacement/amendment/review/publicity signals: CAPTURED"
Write-Host "Statutory effect inference: FORBIDDEN"
Write-Host "Comment/non-document article filtering: ENABLED"
Write-Host "Official article URI validation: ENABLED"
Write-Host "GPP adapter: PRESERVED"
Write-Host "RFN: FAIL-CLOSED"
Write-Host "Document PDF resolution/download: NOT RUN"
Write-Host "DB write: NONE"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "============================================================"
