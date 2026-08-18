$ErrorActionPreference="Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer Phase 2C.2"
Write-Host "Generic Spatial Scope + Import Planning"
Write-Host "NO DB WRITE / NO MIGRATION / SAMPLE-INDEPENDENT"
Write-Host "============================================================"

$root=(Get-Location).Path
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root "artifacts\smart_organizer_phase2c2_backup_$stamp"
$log=Join-Path $root "artifacts\smart_organizer_phase2c2_result.txt"

$api=Join-Path $root "backend\app\api\v1\track_b.py"
$service=Join-Path $root "backend\app\services\track_b_smart_spatial_import_plan.py"
$test=Join-Path $root "backend\tests\test_track_b_smart_spatial_import_plan_phase2c2.py"
$servicePayload=Join-Path $root "track_b_smart_spatial_import_plan.py.txt"
$testPayload=Join-Path $root "test_track_b_smart_spatial_import_plan_phase2c2.py.txt"

foreach($p in @($api,$servicePayload,$testPayload)){
    if(-not(Test-Path $p)){throw "Required file missing: $p"}
}

New-Item -ItemType Directory -Force $backup|Out-Null
Copy-Item $api (Join-Path $backup "track_b.py") -Force
if(Test-Path $service){Copy-Item $service (Join-Path $backup "track_b_smart_spatial_import_plan.py") -Force}
if(Test-Path $test){Copy-Item $test (Join-Path $backup "test_track_b_smart_spatial_import_plan_phase2c2.py") -Force}

function Restore-Backup{
    Copy-Item (Join-Path $backup "track_b.py") $api -Force
    if(Test-Path(Join-Path $backup "track_b_smart_spatial_import_plan.py")){
        Copy-Item (Join-Path $backup "track_b_smart_spatial_import_plan.py") $service -Force
    } elseif(Test-Path $service){Remove-Item $service -Force}
    if(Test-Path(Join-Path $backup "test_track_b_smart_spatial_import_plan_phase2c2.py")){
        Copy-Item (Join-Path $backup "test_track_b_smart_spatial_import_plan_phase2c2.py") $test -Force
    } elseif(Test-Path $test){Remove-Item $test -Force}
}

try{
    Write-Host "BACKUP: $backup"

    Write-Host "[0] Preflight"
    $apiText=Get-Content $api -Raw
    if(-not $apiText.Contains("SMART_ORGANIZER_PHASE2C1_TRANSACTIONAL_SITE") -and
       -not (Test-Path (Join-Path $root "backend\app\services\track_b_smart_transactional_site.py"))){
        throw "Phase 2C.1 baseline missing."
    }
    if(-not $apiText.Contains("SMART_ORGANIZER_PHASE2B3_SITE_RESOLUTION")){
        throw "Phase 2B.3 API baseline missing."
    }
    if($apiText.Contains("SMART_ORGANIZER_PHASE2C2_SPATIAL_IMPORT_PLAN")){
        throw "Phase 2C.2 already installed."
    }
    Write-Host "phase2c1_baseline=CONFIRMED"
    Write-Host "phase2b3_baseline=CONFIRMED"

    Write-Host "[1] Install spatial import planning service + tests"
    Copy-Item $servicePayload $service -Force
    Copy-Item $testPayload $test -Force

    Write-Host "[2] Patch Track B API"
    $imp='from app.services.track_b_smart_site_resolution import SiteResolutionRequest, validate_site_resolution, parse_uploaded_boundary_geojson'
    if(-not $apiText.Contains($imp)){throw "Phase 2B.3 import anchor missing."}
    $apiText=$apiText.Replace(
        $imp,
        $imp+"`r`nfrom app.services.track_b_smart_spatial_import_plan import build_spatial_import_plan"
    )

    $anchor='@router.post("/organizer-intake/site-resolution/validate")'
    $idx=$apiText.IndexOf($anchor)
    if($idx -lt 0){throw "Site resolution route anchor missing."}

    $route=@'
# SMART_ORGANIZER_PHASE2C2_SPATIAL_IMPORT_PLAN
@router.post("/organizer-intake/import-plan")
async def organizer_intake_import_plan(
    project_id: uuid.UUID,
    site_name: str = Form(...),
    site_geometry_json: str = Form(...),
    site_source_ref: str | None = Form(default=None),
    user_confirmed: bool = Form(False),
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        try:
            site_geometry = json.loads(site_geometry_json)
        except Exception as exc:
            raise TrackBError("site_geometry_json must be valid GeoJSON geometry JSON.") from exc

        validated = validate_site_resolution(
            SiteResolutionRequest(
                site_name=site_name,
                mode="manual_draw",
                geometry=site_geometry,
                source_ref=site_source_ref,
                user_confirmed=user_confirmed,
            )
        )
        if not validated.get("ready_for_site_creation"):
            raise TrackBError("Confirmed valid Site boundary is required before import planning.")

        return await build_spatial_import_plan(
            files=files,
            site_geometry=validated["geometry"],
            site_name=validated["site_name"],
            site_source_ref=site_source_ref,
            user_confirmed=True,
        )
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc


'@
    $apiText=$apiText.Insert($idx,$route)

    if(-not $apiText.Contains("import json")){
        $apiText=$apiText.Replace(
            "from __future__ import annotations",
            "from __future__ import annotations`r`n`r`nimport json"
        )
    }

    Set-Content $api $apiText -Encoding UTF8

    Write-Host "[3] Syntax"
    docker compose exec -T backend python -m py_compile `
        /app/app/services/track_b_smart_spatial_import_plan.py `
        /app/app/api/v1/track_b.py
    if($LASTEXITCODE-ne 0){throw "Syntax failed."}

    Write-Host "[4] Focused Phase 2C.2 tests"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_spatial_import_plan_phase2c2.py
    if($LASTEXITCODE-ne 0){throw "Phase 2C.2 focused tests failed."}

    Write-Host "[5] Preserve 2C.1 / 2B.3 / 2A regressions"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_transactional_site_phase2c1.py `
        tests/test_track_b_smart_site_resolution_phase2b3.py `
        tests/test_track_b_smart_site_discovery_phase2b2.py `
        tests/test_track_b_smart_import_phase2a.py
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
t=Path("/app/app/services/track_b_smart_spatial_import_plan.py").read_text()
assert "SMART_ORGANIZER_PHASE2C2_SPATIAL_IMPORT_PLAN" in t
assert "IMPORT_CANDIDATE" in t
assert "SKIP_NO_OVERLAP" in t
assert "SKIP_EMPTY" in t
assert '"database_writes": False' in t
print("runtime_phase2c2_spatial_import_plan=PASS")
'@
    $verify|docker compose exec -T -w /app backend python -
    if($LASTEXITCODE-ne 0){throw "Runtime verification failed."}

    Write-Host "[9] DB safety"
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
SMART ORGANIZER PHASE 2C.2 PASS
============================================================
Generic Site-scoped spatial planning: ENABLED
IMPORT_CANDIDATE decision: ENABLED
SKIP_NO_OVERLAP decision: ENABLED
SKIP_EMPTY decision: ENABLED
Invalid geometry review gate: ENABLED
Per-dataset intersecting feature counts: ENABLED
Role confirmation before persistent import: ENFORCED
Persistent write authorization: FALSE
Database writes: NONE
Migration: NONE
Sample-specific assumptions: NONE
Next gate: LIVE PHASE 2C.2 IMPORT PLAN ACCEPTANCE
============================================================
"@|Tee-Object -FilePath $log

    Write-Host "RESULT SAVED TO: $log"
}
catch{
    Write-Host ""
    Write-Host "INSTALL FAILED - restoring Phase 2C.1 baseline."
    Restore-Backup
    throw
}
