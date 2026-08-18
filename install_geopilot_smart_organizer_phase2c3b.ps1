$ErrorActionPreference="Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer Phase 2C.3B"
Write-Host "Persistent Import All Orchestrator"
Write-Host "ATOMIC SITE + GIS / NO MIGRATION"
Write-Host "============================================================"

$root=(Get-Location).Path
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root "artifacts\smart_organizer_phase2c3b_backup_$stamp"
$log=Join-Path $root "artifacts\smart_organizer_phase2c3b_result.txt"

$api=Join-Path $root "backend\app\api\v1\track_b.py"
$service=Join-Path $root "backend\app\services\track_b_smart_import_all.py"
$test=Join-Path $root "backend\tests\test_track_b_smart_import_all_phase2c3b.py"
$servicePayload=Join-Path $root "track_b_smart_import_all.py.txt"
$testPayload=Join-Path $root "test_track_b_smart_import_all_phase2c3b.py.txt"

foreach($p in @($api,$servicePayload,$testPayload)){
    if(-not(Test-Path $p)){throw "Required file missing: $p"}
}

New-Item -ItemType Directory -Force $backup|Out-Null
Copy-Item $api (Join-Path $backup "track_b.py") -Force
if(Test-Path $service){Copy-Item $service (Join-Path $backup "track_b_smart_import_all.py") -Force}
if(Test-Path $test){Copy-Item $test (Join-Path $backup "test_track_b_smart_import_all_phase2c3b.py") -Force}

function Restore-Backup{
    Copy-Item (Join-Path $backup "track_b.py") $api -Force
    if(Test-Path(Join-Path $backup "track_b_smart_import_all.py")){
        Copy-Item (Join-Path $backup "track_b_smart_import_all.py") $service -Force
    } elseif(Test-Path $service){Remove-Item $service -Force}
    if(Test-Path(Join-Path $backup "test_track_b_smart_import_all_phase2c3b.py")){
        Copy-Item (Join-Path $backup "test_track_b_smart_import_all_phase2c3b.py") $test -Force
    } elseif(Test-Path $test){Remove-Item $test -Force}
}

try{
    Write-Host "BACKUP: $backup"

    Write-Host "[0] Preflight"
    foreach($p in @(
        (Join-Path $root "backend\app\services\track_b_smart_transactional_site.py"),
        (Join-Path $root "backend\app\services\track_b_smart_transactional_gis.py"),
        (Join-Path $root "backend\app\services\track_b_smart_import.py")
    )){
        if(-not(Test-Path $p)){throw "Required previous-phase service missing: $p"}
    }
    $apiText=Get-Content $api -Raw
    if($apiText.Contains("SMART_ORGANIZER_PHASE2C3B_PERSISTENT_IMPORT_ALL")){
        throw "Phase 2C.3B already installed."
    }
    Write-Host "phase2c3a_baseline=CONFIRMED"

    Write-Host "[1] Install persistent Import All service + tests"
    Copy-Item $servicePayload $service -Force
    Copy-Item $testPayload $test -Force

    Write-Host "[2] Patch Track B API"
    $importAnchor='from app.services.track_b_smart_spatial_import_plan import build_spatial_import_plan'
    if(-not $apiText.Contains($importAnchor)){throw "Phase 2C.2 import anchor missing."}
    $apiText=$apiText.Replace(
        $importAnchor,
        $importAnchor+"`r`nfrom app.services.track_b_smart_import_all import ImportAllRequest, execute_persistent_import_all"
    )

    $routeAnchor='@router.post("/organizer-intake/import-plan")'
    $idx=$apiText.IndexOf($routeAnchor)
    if($idx -lt 0){throw "Import plan route anchor missing."}

    $route=@'
# SMART_ORGANIZER_PHASE2C3B_PERSISTENT_IMPORT_ALL
@router.post("/organizer-intake/import-all")
async def organizer_intake_import_all(
    project_id: uuid.UUID,
    site_name: str = Form(...),
    site_geometry_json: str = Form(...),
    site_source_ref: str | None = Form(default=None),
    user_confirmed: bool = Form(False),
    role_assignments_json: str = Form("{}"),
    allow_invalid_geometry_skip: bool = Form(False),
    execute_persistent: bool = Form(False),
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        try:
            site_geometry = json.loads(site_geometry_json)
            role_assignments = json.loads(role_assignments_json)
        except Exception as exc:
            raise TrackBError(
                "site_geometry_json and role_assignments_json must be valid JSON."
            ) from exc
        if not isinstance(role_assignments, dict):
            raise TrackBError("role_assignments_json must be a JSON object.")

        payload = ImportAllRequest(
            site_name=site_name,
            site_geometry=site_geometry,
            site_source_ref=site_source_ref,
            user_confirmed=user_confirmed,
            role_assignments=role_assignments,
            allow_invalid_geometry_skip=allow_invalid_geometry_skip,
            execute_persistent=execute_persistent,
        )
        return await execute_persistent_import_all(
            session,
            owner=current_user,
            project_id=project_id,
            files=files,
            request=payload,
        )
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        session.rollback()
        raise _error(exc, status=500) from exc


'@
    $apiText=$apiText.Insert($idx,$route)
    Set-Content $api $apiText -Encoding UTF8

    Write-Host "[3] Syntax"
    docker compose exec -T backend python -m py_compile `
        /app/app/services/track_b_smart_import_all.py `
        /app/app/api/v1/track_b.py
    if($LASTEXITCODE-ne 0){throw "Syntax failed."}

    Write-Host "[4] Focused 2C.3B tests"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_import_all_phase2c3b.py
    if($LASTEXITCODE-ne 0){throw "Focused 2C.3B tests failed."}

    Write-Host "[5] Preserve previous phase regressions"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_transactional_gis_phase2c3a.py `
        tests/test_track_b_smart_spatial_import_plan_phase2c2.py `
        tests/test_track_b_smart_transactional_site_phase2c1.py `
        tests/test_track_b_smart_site_resolution_phase2b3.py
    if($LASTEXITCODE-ne 0){throw "Existing phase regression failed."}

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
import inspect
from app.services import track_b_smart_import_all as svc
t=Path("/app/app/services/track_b_smart_import_all.py").read_text()
f=inspect.getsource(svc.execute_persistent_import_all)
assert "SMART_ORGANIZER_PHASE2C3B_PERSISTENT_IMPORT_ALL" in t
assert f.count("session.commit()")==1
assert "blocked_no_import_candidates" in f
assert "execute_persistent" in f
assert "role_assignments" in f
assert "allow_invalid_geometry_skip" in f
print("runtime_phase2c3b_import_all=PASS")
'@
    $verify|docker compose exec -T -w /app backend python -
    if($LASTEXITCODE-ne 0){throw "Runtime verification failed."}

    Write-Host "[9] Zero-candidate sample safety acceptance"
    $db=@'
from app.db import get_session_factory
from sqlalchemy import text
with get_session_factory()() as db:
    print("alembic_revision=",db.execute(text("SELECT version_num FROM alembic_version")).scalar())
    print("site_count=",db.execute(text("SELECT COUNT(*) FROM sites")).scalar())
    print("gis_layers=",db.execute(text("SELECT COUNT(*) FROM gis_layers")).scalar())
    print("gis_features=",db.execute(text("SELECT COUNT(*) FROM gis_features")).scalar())
'@
    $db|docker compose exec -T -w /app backend python -
    if($LASTEXITCODE-ne 0){throw "DB safety check failed."}

    @"
============================================================
SMART ORGANIZER PHASE 2C.3B PASS
============================================================
Persistent Import All orchestrator: ENABLED
One atomic transaction for Site + GIS: ENABLED
Explicit Site confirmation: ENFORCED
Explicit per-dataset role assignment: ENFORCED
Zero import candidate fallback: BLOCKED
Invalid geometry silent skip: BLOCKED BY DEFAULT
Spatial filter: INTERSECTS CONFIRMED SITE
Source geometry preservation: ENABLED
Layer provenance/checksum: ENABLED
Layer/feature duplicate protection: ENABLED
Dry-run / ready-for-commit mode: ENABLED
Persistent commit: EXPLICIT ONLY
Migration: NONE
Sample-specific assumptions: NONE
Next gate: PHASE 2C.3B CONTROLLED COMMIT ACCEPTANCE
============================================================
"@|Tee-Object -FilePath $log

    Write-Host "RESULT SAVED TO: $log"
}
catch{
    Write-Host ""
    Write-Host "INSTALL FAILED - restoring Phase 2C.3A baseline."
    Restore-Backup
    throw
}
