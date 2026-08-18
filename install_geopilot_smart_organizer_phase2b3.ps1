$ErrorActionPreference="Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer Phase 2B.3"
Write-Host "Generic Site Resolution Fallback + Confirmation Gate"
Write-Host "SAMPLE-INDEPENDENT / NO DB WRITE / NO MIGRATION"
Write-Host "============================================================"

$root=(Get-Location).Path
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root "artifacts\smart_organizer_phase2b3_backup_$stamp"
$log=Join-Path $root "artifacts\smart_organizer_phase2b3_result.txt"

$api=Join-Path $root "backend\app\api\v1\track_b.py"
$service=Join-Path $root "backend\app\services\track_b_smart_site_resolution.py"
$test=Join-Path $root "backend\tests\test_track_b_smart_site_resolution_phase2b3.py"
$servicePayload=Join-Path $root "track_b_smart_site_resolution.py.txt"
$testPayload=Join-Path $root "test_track_b_smart_site_resolution_phase2b3.py.txt"

foreach($p in @($api,$servicePayload,$testPayload)){
    if(-not(Test-Path $p)){throw "Required file missing: $p"}
}

New-Item -ItemType Directory -Force $backup|Out-Null
Copy-Item $api (Join-Path $backup "track_b.py") -Force
if(Test-Path $service){Copy-Item $service (Join-Path $backup "track_b_smart_site_resolution.py") -Force}
if(Test-Path $test){Copy-Item $test (Join-Path $backup "test_track_b_smart_site_resolution_phase2b3.py") -Force}

function Restore-Backup{
    Copy-Item (Join-Path $backup "track_b.py") $api -Force
    if(Test-Path(Join-Path $backup "track_b_smart_site_resolution.py")){
        Copy-Item (Join-Path $backup "track_b_smart_site_resolution.py") $service -Force
    } elseif(Test-Path $service){
        Remove-Item $service -Force
    }
    if(Test-Path(Join-Path $backup "test_track_b_smart_site_resolution_phase2b3.py")){
        Copy-Item (Join-Path $backup "test_track_b_smart_site_resolution_phase2b3.py") $test -Force
    } elseif(Test-Path $test){
        Remove-Item $test -Force
    }
}

try{
    Write-Host "BACKUP: $backup"

    Write-Host "[0] Preflight"
    $apiText=Get-Content $api -Raw
    if(-not $apiText.Contains("SMART_ORGANIZER_PHASE2B2_SITE_DISCOVERY")){
        throw "Phase 2B.2 baseline missing."
    }
    if($apiText.Contains("SMART_ORGANIZER_PHASE2B3_SITE_RESOLUTION")){
        throw "Phase 2B.3 already installed."
    }
    Write-Host "phase2b2_baseline=CONFIRMED"

    Write-Host "[1] Install generic Site resolution service + tests"
    Copy-Item $servicePayload $service -Force
    Copy-Item $testPayload $test -Force

    Write-Host "[2] Patch Track B API"
    $imp='from app.services.track_b_smart_site_discovery import discover_site_candidates'
    if(-not $apiText.Contains($imp)){throw "Phase 2B.2 import anchor missing."}
    $apiText=$apiText.Replace(
        $imp,
        $imp+"`r`nfrom app.services.track_b_smart_site_resolution import SiteResolutionRequest, validate_site_resolution, parse_uploaded_boundary_geojson"
    )

    $anchor='@router.post("/organizer-intake/site-candidates")'
    $idx=$apiText.IndexOf($anchor)
    if($idx -lt 0){throw "Phase 2B.2 route anchor missing."}

    $route=@'
# SMART_ORGANIZER_PHASE2B3_SITE_RESOLUTION
@router.post("/organizer-intake/site-resolution/validate")
async def organizer_intake_site_resolution_validate(
    project_id: uuid.UUID,
    payload: SiteResolutionRequest,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        return validate_site_resolution(payload)
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc


@router.post("/organizer-intake/site-resolution/upload")
async def organizer_intake_site_resolution_upload(
    project_id: uuid.UUID,
    site_name: str = Form(...),
    user_confirmed: bool = Form(False),
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        data = await file.read()
        return parse_uploaded_boundary_geojson(
            site_name=site_name,
            payload=data,
            source_ref=file.filename or "uploaded_boundary",
            user_confirmed=user_confirmed,
        )
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc


'@
    $apiText=$apiText.Insert($idx,$route)

    if($apiText -notmatch 'from fastapi import .*\bForm\b'){
        $apiText=$apiText -replace 'from fastapi import ([^\r\n]+)', {
            param($m)
            $line=$m.Value
            if($line -match '\bForm\b'){return $line}
            return $line.TrimEnd()+', Form'
        }
    }

    Set-Content $api $apiText -Encoding UTF8

    Write-Host "[3] Syntax"
    docker compose exec -T backend python -m py_compile `
        /app/app/services/track_b_smart_site_resolution.py `
        /app/app/api/v1/track_b.py
    if($LASTEXITCODE-ne 0){throw "Syntax failed."}

    Write-Host "[4] Focused Phase 2B.3 tests"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_site_resolution_phase2b3.py
    if($LASTEXITCODE-ne 0){throw "Phase 2B.3 focused tests failed."}

    Write-Host "[5] Preserve Phase 2A / 2B.2 / Smart Organizer regressions"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_import_phase2a.py `
        tests/test_track_b_smart_site_discovery_phase2b2.py `
        tests/test_track_b_smart_organizer_intake_v1.py `
        tests/test_track_b_smart_organizer_zip_v1_2_2.py `
        tests/test_track_b_smart_organizer_gis_bundle_v1_3.py `
        tests/test_track_b_smart_organizer_format_coverage_v1_3_3.py
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
t=Path("/app/app/services/track_b_smart_site_resolution.py").read_text()
assert "SMART_ORGANIZER_PHASE2B3_SITE_RESOLUTION" in t
assert "confirmation_required" in t
assert "uploaded_boundary" in t
assert "manual_draw" in t
assert "organizer_candidate" in t
print("runtime_phase2b3_site_resolution=PASS")
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
SMART ORGANIZER PHASE 2B.3 PASS
============================================================
Organizer candidate boundary confirmation: ENABLED
Uploaded GeoJSON boundary fallback: ENABLED
Manual/drawn Polygon/MultiPolygon fallback: ENABLED
EPSG:4326 geometry validation: ENFORCED
Explicit user confirmation: ENFORCED
Automatic Site creation: STILL DISABLED
Database writes: NONE
Migration: NONE
Sample-specific assumptions: NONE
Next gate: LIVE GENERIC SITE RESOLUTION ACCEPTANCE
============================================================
"@|Tee-Object -FilePath $log

    Write-Host "RESULT SAVED TO: $log"
}
catch{
    Write-Host ""
    Write-Host "INSTALL FAILED - restoring Phase 2B.2 baseline."
    Restore-Backup
    throw
}
