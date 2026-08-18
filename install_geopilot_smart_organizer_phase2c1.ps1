$ErrorActionPreference="Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer Phase 2C.1"
Write-Host "Transactional Competition Site Creation Foundation"
Write-Host "NO MIGRATION / ACCEPTANCE WRITES ROLLED BACK"
Write-Host "============================================================"

$root=(Get-Location).Path
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root "artifacts\smart_organizer_phase2c1_backup_$stamp"
$log=Join-Path $root "artifacts\smart_organizer_phase2c1_result.txt"

$service=Join-Path $root "backend\app\services\track_b_smart_transactional_site.py"
$test=Join-Path $root "backend\tests\test_track_b_smart_transactional_site_phase2c1.py"
$servicePayload=Join-Path $root "track_b_smart_transactional_site.py.txt"
$testPayload=Join-Path $root "test_track_b_smart_transactional_site_phase2c1.py.txt"

foreach($p in @($servicePayload,$testPayload)){
    if(-not(Test-Path $p)){throw "Required payload missing: $p"}
}

New-Item -ItemType Directory -Force $backup|Out-Null
if(Test-Path $service){Copy-Item $service (Join-Path $backup "track_b_smart_transactional_site.py") -Force}
if(Test-Path $test){Copy-Item $test (Join-Path $backup "test_track_b_smart_transactional_site_phase2c1.py") -Force}

function Restore-Backup{
    if(Test-Path(Join-Path $backup "track_b_smart_transactional_site.py")){
        Copy-Item (Join-Path $backup "track_b_smart_transactional_site.py") $service -Force
    } elseif(Test-Path $service){Remove-Item $service -Force}
    if(Test-Path(Join-Path $backup "test_track_b_smart_transactional_site_phase2c1.py")){
        Copy-Item (Join-Path $backup "test_track_b_smart_transactional_site_phase2c1.py") $test -Force
    } elseif(Test-Path $test){Remove-Item $test -Force}
}

try{
    Write-Host "BACKUP: $backup"

    Write-Host "[0] Preflight exact architecture"
    $pre=@'
from app.models.site import Site
from pathlib import Path
import inspect
from app.services import sites

assert Site.__table__.c.geometry_hash is not None
assert Site.__table__.c.geometry_revision is not None
src=inspect.getsource(sites.create_site)
assert "session.commit()" in src
assert "session.flush()" not in src
print("existing_site_commit_boundary=CONFIRMED")
print("site_geometry_hash=CONFIRMED")
print("site_geometry_revision=CONFIRMED")
'@
    $pre|docker compose exec -T -w /app backend python -
    if($LASTEXITCODE-ne 0){throw "Preflight architecture mismatch."}

    Write-Host "[1] Install transaction-aware service + focused tests"
    Copy-Item $servicePayload $service -Force
    Copy-Item $testPayload $test -Force

    Write-Host "[2] Syntax"
    docker compose exec -T backend python -m py_compile `
        /app/app/services/track_b_smart_transactional_site.py
    if($LASTEXITCODE-ne 0){throw "Syntax failed."}

    Write-Host "[3] Focused static contract tests"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_transactional_site_phase2c1.py
    if($LASTEXITCODE-ne 0){throw "Focused Phase 2C.1 tests failed."}

    Write-Host "[4] Transactional live rollback acceptance"
    $accept=@'
import uuid
from sqlalchemy import select, func
from app.db import get_session_factory
from app.models.project import Project
from app.models.site import Site
from app.models.user import User
from app.schemas.site import SiteCreateRequest
from app.services.track_b_smart_transactional_site import create_competition_site_uncommitted

SessionFactory=get_session_factory()
db=SessionFactory()
try:
    project=db.scalar(select(Project).where(Project.is_archived.is_(False)).order_by(Project.created_at.asc()))
    assert project is not None, "No non-archived project available for rollback acceptance."
    owner=db.get(User, project.owner_id)
    assert owner is not None, "Project owner missing."

    before=db.scalar(select(func.count()).select_from(Site))
    active_before=db.scalar(
        select(func.count()).select_from(Site).where(
            Site.project_id==project.id,
            Site.is_active.is_(True),
            Site.is_archived.is_(False),
        )
    )

    fixture_name="PHASE2C1_ROLLBACK_FIXTURE_"+uuid.uuid4().hex[:8]
    geometry={
        "type":"Polygon",
        "coordinates":[[
            [101.5000,3.0500],
            [101.5100,3.0500],
            [101.5100,3.0600],
            [101.5000,3.0600],
            [101.5000,3.0500],
        ]],
    }

    result=create_competition_site_uncommitted(
        db,
        owner=owner,
        project_id=project.id,
        request=SiteCreateRequest(
            name=fixture_name,
            geometry=geometry,
            is_active=True,
        ),
    )
    assert result.created is True
    assert result.duplicate is False
    assert result.site.id is not None

    during=db.scalar(select(func.count()).select_from(Site))
    assert during==before+1

    duplicate=create_competition_site_uncommitted(
        db,
        owner=owner,
        project_id=project.id,
        request=SiteCreateRequest(
            name=fixture_name+" DUPLICATE",
            geometry=geometry,
            is_active=True,
        ),
    )
    assert duplicate.created is False
    assert duplicate.duplicate is True
    assert duplicate.site.id==result.site.id

    db.rollback()

    after=db.scalar(select(func.count()).select_from(Site))
    active_after=db.scalar(
        select(func.count()).select_from(Site).where(
            Site.project_id==project.id,
            Site.is_active.is_(True),
            Site.is_archived.is_(False),
        )
    )
    fixture_after=db.scalar(
        select(func.count()).select_from(Site).where(Site.name==fixture_name)
    )

    assert after==before
    assert active_after==active_before
    assert fixture_after==0

    print("transactional_site_create=PASS")
    print("duplicate_guard=PASS")
    print("rollback_site_count_restored=PASS")
    print("rollback_active_state_restored=PASS")
    print("fixture_persisted=0")
finally:
    db.rollback()
    db.close()
'@
    $accept|docker compose exec -T -w /app backend python -
    if($LASTEXITCODE-ne 0){throw "Transactional rollback acceptance failed."}

    Write-Host "[5] Existing Smart Organizer regression"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_site_resolution_phase2b3.py `
        tests/test_track_b_smart_site_discovery_phase2b2.py `
        tests/test_track_b_smart_import_phase2a.py
    if($LASTEXITCODE-ne 0){throw "Existing Smart Organizer regression failed."}

    Write-Host "[6] Full backend regression"
    docker compose exec -T backend python -m pytest -q
    if($LASTEXITCODE-ne 0){throw "Full backend regression failed."}

    Write-Host "[7] Recreate backend"
    docker compose up -d --force-recreate backend
    if($LASTEXITCODE-ne 0){throw "Backend recreate failed."}
    Start-Sleep -Seconds 8
    docker compose ps backend

    Write-Host "[8] Final DB preservation gate"
    $db=@'
from app.db import get_session_factory
from sqlalchemy import text
with get_session_factory()() as db:
    print("alembic_revision=",db.execute(text("SELECT version_num FROM alembic_version")).scalar())
    print("site_count=",db.execute(text("SELECT COUNT(*) FROM sites")).scalar())
    print("gis_layers=",db.execute(text("SELECT COUNT(*) FROM gis_layers")).scalar())
    print("gis_features=",db.execute(text("SELECT COUNT(*) FROM gis_features")).scalar())
    print("phase2c1_fixture_count=",db.execute(text("SELECT COUNT(*) FROM sites WHERE name LIKE 'PHASE2C1_ROLLBACK_FIXTURE_%'")).scalar())
'@
    $db|docker compose exec -T -w /app backend python -
    if($LASTEXITCODE-ne 0){throw "Final DB preservation gate failed."}

    @"
============================================================
SMART ORGANIZER PHASE 2C.1 PASS
============================================================
Transaction-aware Competition Site creation: ENABLED
Existing Site model/schema reused: YES
Existing /sites API behavior changed: NO
Duplicate protection: project_id + geometry_hash
Active Site lifecycle: PRESERVED
Internal transaction behavior: FLUSH ONLY
Caller-owned commit/rollback: ENABLED
Rollback acceptance: PASS
Acceptance fixture persisted: NO
Migration: NONE
Next gate: PHASE 2C.2 SPATIAL SCOPE + IMPORT PLANNING
============================================================
"@|Tee-Object -FilePath $log

    Write-Host "RESULT SAVED TO: $log"
}
catch{
    Write-Host ""
    Write-Host "INSTALL FAILED - restoring previous baseline."
    Restore-Backup
    throw
}
