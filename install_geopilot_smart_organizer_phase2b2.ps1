$ErrorActionPreference="Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer Phase 2B.2"
Write-Host "Organizer Site Discovery & Assignment Foundation"
Write-Host "NO SITE CREATE / NO GIS DB WRITE / NO MIGRATION"
Write-Host "============================================================"

$root=(Get-Location).Path
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root "artifacts\smart_organizer_phase2b2_backup_$stamp"
$log=Join-Path $root "artifacts\smart_organizer_phase2b2_result.txt"
$api=Join-Path $root "backend\app\api\v1\track_b.py"
$service=Join-Path $root "backend\app\services\track_b_smart_site_discovery.py"
$test=Join-Path $root "backend\tests\test_track_b_smart_site_discovery_phase2b2.py"
$servicePayload=Join-Path $root "track_b_smart_site_discovery.py.txt"
$testPayload=Join-Path $root "test_track_b_smart_site_discovery_phase2b2.py.txt"

foreach($p in @($api,$servicePayload,$testPayload)){if(-not(Test-Path $p)){throw "Required file missing: $p"}}
New-Item -ItemType Directory -Force $backup|Out-Null
Copy-Item $api (Join-Path $backup "track_b.py") -Force
if(Test-Path $service){Copy-Item $service (Join-Path $backup "track_b_smart_site_discovery.py") -Force}
if(Test-Path $test){Copy-Item $test (Join-Path $backup "test_track_b_smart_site_discovery_phase2b2.py") -Force}

function Restore-Backup{
 Copy-Item (Join-Path $backup "track_b.py") $api -Force
 if(Test-Path(Join-Path $backup "track_b_smart_site_discovery.py")){Copy-Item (Join-Path $backup "track_b_smart_site_discovery.py") $service -Force}elseif(Test-Path $service){Remove-Item $service -Force}
 if(Test-Path(Join-Path $backup "test_track_b_smart_site_discovery_phase2b2.py")){Copy-Item (Join-Path $backup "test_track_b_smart_site_discovery_phase2b2.py") $test -Force}elseif(Test-Path $test){Remove-Item $test -Force}
}

try{
 Write-Host "BACKUP: $backup"
 Write-Host "[0] Preflight"
 $apiText=Get-Content $api -Raw
 if(-not $apiText.Contains("SMART_ORGANIZER_PHASE2A")){throw "Phase 2A baseline missing."}
 if($apiText.Contains("SMART_ORGANIZER_PHASE2B2_SITE_DISCOVERY")){throw "Phase 2B.2 already present."}
 Write-Host "phase2a_baseline=CONFIRMED"

 Write-Host "[1] Install Site discovery service + tests"
 Copy-Item $servicePayload $service -Force
 Copy-Item $testPayload $test -Force

 Write-Host "[2] Patch Track B API"
 $imp='from app.services.track_b_smart_import import prepare_import_plan'
 if(-not $apiText.Contains($imp)){throw "Phase 2A API import anchor missing."}
 $apiText=$apiText.Replace($imp,$imp+"`r`nfrom app.services.track_b_smart_site_discovery import discover_site_candidates")
 $anchor='@router.post("/organizer-intake/prepare")'
 $idx=$apiText.IndexOf($anchor)
 if($idx -lt 0){throw "Phase 2A prepare route anchor missing."}
 $route=@'
# SMART_ORGANIZER_PHASE2B2_SITE_DISCOVERY
@router.post("/organizer-intake/site-candidates")
async def organizer_intake_site_candidates(
    project_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        return await discover_site_candidates(files)
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc


'@
 $apiText=$apiText.Insert($idx,$route)
 Set-Content $api $apiText -Encoding UTF8

 Write-Host "[3] Syntax"
 docker compose exec -T backend python -m py_compile /app/app/services/track_b_smart_site_discovery.py /app/app/api/v1/track_b.py
 if($LASTEXITCODE-ne 0){throw "Syntax failed."}

 Write-Host "[4] Focused Site discovery tests"
 docker compose exec -T backend python -m pytest -q tests/test_track_b_smart_site_discovery_phase2b2.py
 if($LASTEXITCODE-ne 0){throw "Phase 2B.2 focused tests failed."}

 Write-Host "[5] Preserve Phase 2A + Smart Organizer regressions"
 docker compose exec -T backend python -m pytest -q tests/test_track_b_smart_import_phase2a.py tests/test_track_b_smart_organizer_intake_v1.py tests/test_track_b_smart_organizer_zip_v1_2_2.py tests/test_track_b_smart_organizer_gis_bundle_v1_3.py tests/test_track_b_smart_organizer_format_coverage_v1_3_3.py
 if($LASTEXITCODE-ne 0){throw "Existing regression failed."}

 Write-Host "[6] Full backend regression"
 docker compose exec -T backend python -m pytest -q
 if($LASTEXITCODE-ne 0){throw "Full backend regression failed."}

 Write-Host "[7] Recreate backend"
 docker compose up -d --force-recreate backend
 if($LASTEXITCODE-ne 0){throw "Backend recreate failed."}
 Start-Sleep -Seconds 8
 docker compose ps backend

 Write-Host "[8] Runtime contract"
 $verify=@'
from pathlib import Path
t=Path("/app/app/services/track_b_smart_site_discovery.py").read_text()
assert "SMART_ORGANIZER_PHASE2B2_SITE_DISCOVERY" in t
assert "auto_create_site" in t
assert '"database_writes":False' in t
print("runtime_phase2b2_site_discovery=PASS")
'@
 $verify|docker compose exec -T -w /app backend python -
 if($LASTEXITCODE-ne 0){throw "Runtime verification failed."}

 Write-Host "[9] DB safety"
 $db=@'
from app.db import get_session_factory
from sqlalchemy import text
with get_session_factory()() as db:
    print("alembic_revision=",db.execute(text("SELECT version_num FROM alembic_version")).scalar())
    print("gis_layers=",db.execute(text("SELECT COUNT(*) FROM gis_layers")).scalar())
    print("gis_features=",db.execute(text("SELECT COUNT(*) FROM gis_features")).scalar())
'@
 $db|docker compose exec -T -w /app backend python -
 if($LASTEXITCODE-ne 0){throw "DB safety check failed."}

 @"
============================================================
SMART ORGANIZER PHASE 2B.2 PASS
============================================================
Organizer Site candidate discovery: ENABLED
Strong/review/empty boundary classification: ENABLED
Large parcel layers auto-rejected as Site boundary: ENABLED
Automatic Site creation: DISABLED
User confirmation before Site creation: ENFORCED
Database writes: NONE
Migration: NONE
Next gate: LIVE ORGANIZER SITE DISCOVERY
============================================================
"@|Tee-Object -FilePath $log
 Write-Host "RESULT SAVED TO: $log"
}
catch{
 Write-Host ""
 Write-Host "INSTALL FAILED - restoring backup."
 Restore-Backup
 throw
}
