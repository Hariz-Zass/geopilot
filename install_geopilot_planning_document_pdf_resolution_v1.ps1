$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service = "backend\app\services\planning_document_acquisition.py"
$Tests = "backend\tests\test_planning_document_acquisition.py"
if (!(Test-Path $Service)) { throw "Missing acquisition service." }
if (!(Test-Path $Tests)) { throw "Missing acquisition tests." }

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = "artifacts\planning_document_pdf_resolution_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Service "$Backup\planning_document_acquisition.py"
Copy-Item $Tests "$Backup\test_planning_document_acquisition.py"

Write-Host "============================================================"
Write-Host "GeoPilot Planning Document PDF Resolution + Safe Download V1"
Write-Host "NO DB WRITE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"

Write-Host "[1] Stage helpers"
Copy-Item "$Root\_planning_pdf_resolver_patch_v1.py" "backend\_planning_pdf_resolver_patch_v1.py" -Force
Copy-Item "$Root\_planning_pdf_resolver_tests_v1.py" "backend\_planning_pdf_resolver_tests_v1.py" -Force

try {
    Write-Host "[2] Apply resolver patch"
    docker compose exec -T backend python /app/_planning_pdf_resolver_patch_v1.py
    if ($LASTEXITCODE -ne 0) { throw "Resolver patch failed." }

    Write-Host "[3] Install resolver tests"
    docker compose exec -T backend python /app/_planning_pdf_resolver_tests_v1.py
    if ($LASTEXITCODE -ne 0) { throw "Resolver test patch failed." }
}
finally {
    Remove-Item "backend\_planning_pdf_resolver_patch_v1.py" -Force -ErrorAction SilentlyContinue
    Remove-Item "backend\_planning_pdf_resolver_tests_v1.py" -Force -ErrorAction SilentlyContinue
}

Write-Host "[4] Syntax checks"
docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Syntax check failed." }

Write-Host "[5] Acquisition regression"
docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Acquisition regression failed." }

Write-Host "[6] Existing retrieval regression"
docker compose exec -T backend python -m pytest -q tests/test_document_retrieval.py
if ($LASTEXITCODE -ne 0) { throw "Document retrieval regression failed." }

Write-Host "[7] LIVE ePublisiti article -> PDF resolution"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import *; p=PlanMalaysiaOfficialProvider(); c=PlanningDocumentCandidate(document_class='RKK',title='Draf Rancangan Kawasan Khas Tasik Chini (Pengubahan)',authority='PLANMalaysia',jurisdiction='Pahang',source_uri='https://www.planmalaysia.gov.my/epublisiti/article?id=265d414a-faa1-11f0-9f27-00163e067130',provider='planmalaysia_official',metadata={'document_status':'unverified'}); xs=p.resolve_candidate_pdf_links(c); print('resolved_pdf_links=',len(xs)); [print('-',x.title,'=>',x.source_uri) for x in xs]; assert xs"
if ($LASTEXITCODE -ne 0) { throw "Live PDF resolution failed." }

Write-Host "[8] LIVE safe download first resolved PDF (memory only)"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import *; p=PlanMalaysiaOfficialProvider(); c=PlanningDocumentCandidate(document_class='RKK',title='Draf Rancangan Kawasan Khas Tasik Chini (Pengubahan)',authority='PLANMalaysia',jurisdiction='Pahang',source_uri='https://www.planmalaysia.gov.my/epublisiti/article?id=265d414a-faa1-11f0-9f27-00163e067130',provider='planmalaysia_official',metadata={'document_status':'unverified'}); x=p.resolve_candidate_pdf_links(c)[0]; a=acquire_candidate(x); print('download_bytes=',len(a.content)); print('sha256=',a.checksum_sha256); print('final_uri=',a.final_uri); assert a.content.startswith(b'%PDF-')"
if ($LASTEXITCODE -ne 0) { throw "Live safe PDF download failed." }

Write-Host "[9] GPP preservation"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; xs=PlanMalaysiaOfficialProvider().discover(document_class='GPP',jurisdiction=None,query='tanah tinggi'); print('GPP=',len(xs)); assert xs"
if ($LASTEXITCODE -ne 0) { throw "GPP preservation failed." }

Write-Host "[10] Service health"
docker compose ps

Write-Host "============================================================"
Write-Host "PLANNING DOCUMENT PDF RESOLUTION + SAFE DOWNLOAD V1 PASS"
Write-Host "============================================================"
Write-Host "ePublisiti article -> official PDF links: ENABLED"
Write-Host "GPP direct PDF resolution: PRESERVED"
Write-Host "Official-host validation: PRESERVED"
Write-Host "PDF magic validation: PRESERVED"
Write-Host "SHA-256 generation: PRESERVED"
Write-Host "Live official PDF download: PASS"
Write-Host "Persistent document ingestion: NOT RUN"
Write-Host "OCR/indexing: NOT RUN"
Write-Host "DB write: NONE"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "RFN: FAIL-CLOSED"
Write-Host "============================================================"
