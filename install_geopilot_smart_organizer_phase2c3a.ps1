$ErrorActionPreference="Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer Phase 2C.3A"
Write-Host "Transaction-Aware GIS Write Foundation"
Write-Host "NO MIGRATION / LIVE ACCEPTANCE ROLLED BACK"
Write-Host "============================================================"

$root=(Get-Location).Path
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root "artifacts\smart_organizer_phase2c3a_backup_$stamp"
$log=Join-Path $root "artifacts\smart_organizer_phase2c3a_result.txt"

$service=Join-Path $root "backend\app\services\track_b_smart_transactional_gis.py"
$test=Join-Path $root "backend\tests\test_track_b_smart_transactional_gis_phase2c3a.py"
$servicePayload=Join-Path $root "track_b_smart_transactional_gis.py.txt"
$testPayload=Join-Path $root "test_track_b_smart_transactional_gis_phase2c3a.py.txt"

foreach($p in @($servicePayload,$testPayload)){
    if(-not(Test-Path $p)){throw "Required payload missing: $p"}
}

New-Item -ItemType Directory -Force $backup|Out-Null
if(Test-Path $service){Copy-Item $service (Join-Path $backup "track_b_smart_transactional_gis.py") -Force}
if(Test-Path $test){Copy-Item $test (Join-Path $backup "test_track_b_smart_transactional_gis_phase2c3a.py") -Force}

function Restore-Backup{
    if(Test-Path(Join-Path $backup "track_b_smart_transactional_gis.py")){
        Copy-Item (Join-Path $backup "track_b_smart_transactional_gis.py") $service -Force
    } elseif(Test-Path $service){Remove-Item $service -Force}
    if(Test-Path(Join-Path $backup "test_track_b_smart_transactional_gis_phase2c3a.py")){
        Copy-Item (Join-Path $backup "test_track_b_smart_transactional_gis_phase2c3a.py") $test -Force
    } elseif(Test-Path $test){Remove-Item $test -Force}
}

try{
    Write-Host "BACKUP: $backup"

    Write-Host "[0] Exact architecture preflight"
    $pre=@'
import inspect
from app.services import gis_layers, gis_features
from app.models.gis_layer import GISLayer
from app.models.gis_feature import GISFeature

assert "session.commit()" in inspect.getsource(gis_layers.create_gis_layer)
assert "session.commit()" in inspect.getsource(gis_features.ingest_feature_collection)
assert GISLayer.__table__.c.source_checksum_sha256 is not None
assert GISFeature.__table__.c.geometry_hash is not None
assert GISFeature.__table__.c.source_feature_id is not None
print("existing_commit_boundaries=CONFIRMED")
print("gis_layer_checksum=CONFIRMED")
print("gis_feature_identity=CONFIRMED")
'@
    $pre|docker compose exec -T -w /app backend python -
    if($LASTEXITCODE-ne 0){throw "2C.3A architecture preflight failed."}

    Write-Host "[1] Install transaction-aware GIS service + tests"
    Copy-Item $servicePayload $service -Force
    Copy-Item $testPayload $test -Force

    Write-Host "[2] Syntax"
    docker compose exec -T backend python -m py_compile `
        /app/app/services/track_b_smart_transactional_gis.py
    if($LASTEXITCODE-ne 0){throw "Syntax failed."}

    Write-Host "[3] Focused 2C.3A contract tests"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_transactional_gis_phase2c3a.py
    if($LASTEXITCODE-ne 0){throw "Focused 2C.3A tests failed."}

    Write-Host "[4] Live atomic GIS rollback acceptance"
    $accept=@'
import uuid
from sqlalchemy import select, func
from app.db import get_session_factory
from app.models.project import Project
from app.models.user import User
from app.models.gis_layer import GISLayer
from app.models.gis_feature import GISFeature
from app.schemas.gis_layer import GISLayerCreateRequest
from app.schemas.gis_feature import GISFeatureInput
from app.services.track_b_smart_transactional_gis import (
    create_gis_layer_uncommitted,
    ingest_features_uncommitted,
)

db=get_session_factory()()
try:
    project=db.scalar(
        select(Project)
        .where(Project.is_archived.is_(False))
        .order_by(Project.created_at.asc())
    )
    assert project is not None, "No non-archived project available."
    owner=db.get(User, project.owner_id)
    assert owner is not None, "Project owner missing."

    layers_before=db.scalar(select(func.count()).select_from(GISLayer))
    features_before=db.scalar(select(func.count()).select_from(GISFeature))

    checksum=uuid.uuid4().hex + uuid.uuid4().hex
    role="land_use"

    request=GISLayerCreateRequest(
        name="PHASE2C3A ROLLBACK LAYER",
        description="Temporary transaction acceptance only",
        source_kind="upload",
        source_name="phase2c3a_fixture.geojson",
        source_checksum_sha256=checksum,
        source_crs="EPSG:4326",
        geometry_type="Polygon",
        provenance={
            "applicability_role":role,
            "acceptance_fixture":True,
            "import_method":"smart_organizer_phase2c3a",
        },
        is_active=True,
    )

    layer_result=create_gis_layer_uncommitted(
        db,
        owner=owner,
        project_id=project.id,
        request=request,
    )
    assert layer_result.created is True
    assert layer_result.duplicate is False

    duplicate_layer=create_gis_layer_uncommitted(
        db,
        owner=owner,
        project_id=project.id,
        request=request,
    )
    assert duplicate_layer.created is False
    assert duplicate_layer.duplicate is True
    assert duplicate_layer.layer.id==layer_result.layer.id

    poly={
        "type":"Polygon",
        "coordinates":[[
            [101.5000,3.0500],
            [101.5010,3.0500],
            [101.5010,3.0510],
            [101.5000,3.0510],
            [101.5000,3.0500],
        ]],
    }

    items=[
        GISFeatureInput(
            type="Feature",
            id="fixture-1",
            geometry=poly,
            properties={"fixture":True},
        ),
        GISFeatureInput(
            type="Feature",
            id="fixture-2",
            geometry={
                "type":"Polygon",
                "coordinates":[[
                    [101.5020,3.0520],
                    [101.5030,3.0520],
                    [101.5030,3.0530],
                    [101.5020,3.0530],
                    [101.5020,3.0520],
                ]],
            },
            properties={"fixture":True},
        ),
    ]

    batch=ingest_features_uncommitted(
        db,
        layer=layer_result.layer,
        features=items,
    )
    assert batch.created_count==2
    assert batch.duplicate_count==0

    duplicate_batch=ingest_features_uncommitted(
        db,
        layer=layer_result.layer,
        features=items,
    )
    assert duplicate_batch.created_count==0
    assert duplicate_batch.duplicate_count==2

    layers_during=db.scalar(select(func.count()).select_from(GISLayer))
    features_during=db.scalar(select(func.count()).select_from(GISFeature))
    assert layers_during==layers_before+1
    assert features_during==features_before+2

    db.rollback()

    layers_after=db.scalar(select(func.count()).select_from(GISLayer))
    features_after=db.scalar(select(func.count()).select_from(GISFeature))
    fixture_layers=db.scalar(
        select(func.count()).select_from(GISLayer).where(
            GISLayer.source_checksum_sha256==checksum
        )
    )

    assert layers_after==layers_before
    assert features_after==features_before
    assert fixture_layers==0

    print("transactional_gis_layer_create=PASS")
    print("transactional_gis_feature_ingest=PASS")
    print("layer_duplicate_guard=PASS")
    print("feature_duplicate_guard=PASS")
    print("rollback_layer_count_restored=PASS")
    print("rollback_feature_count_restored=PASS")
    print("acceptance_fixture_persisted=0")
finally:
    db.rollback()
    db.close()
'@
    $accept|docker compose exec -T -w /app backend python -
    if($LASTEXITCODE-ne 0){throw "Live atomic GIS rollback acceptance failed."}

    Write-Host "[5] Preserve Smart Organizer phase regressions"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_spatial_import_plan_phase2c2.py `
        tests/test_track_b_smart_transactional_site_phase2c1.py `
        tests/test_track_b_smart_site_resolution_phase2b3.py `
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
t=Path("/app/app/services/track_b_smart_transactional_gis.py").read_text()
assert "SMART_ORGANIZER_PHASE2C3A_TRANSACTIONAL_GIS" in t
assert "session.commit" not in t
assert "session.rollback" not in t
assert "session.flush()" in t
assert "source_checksum_sha256" in t
assert "source_feature_id" in t
assert "geometry_hash" in t
print("runtime_phase2c3a_transactional_gis=PASS")
'@
    $verify|docker compose exec -T -w /app backend python -
    if($LASTEXITCODE-ne 0){throw "Runtime verification failed."}

    Write-Host "[9] Final DB preservation"
    $db=@'
from app.db import get_session_factory
from sqlalchemy import text
with get_session_factory()() as db:
    print("alembic_revision=",db.execute(text("SELECT version_num FROM alembic_version")).scalar())
    print("site_count=",db.execute(text("SELECT COUNT(*) FROM sites")).scalar())
    print("gis_layers=",db.execute(text("SELECT COUNT(*) FROM gis_layers")).scalar())
    print("gis_features=",db.execute(text("SELECT COUNT(*) FROM gis_features")).scalar())
    print("phase2c3a_fixture_layers=",db.execute(text("SELECT COUNT(*) FROM gis_layers WHERE source_name='phase2c3a_fixture.geojson'")).scalar())
'@
    $db|docker compose exec -T -w /app backend python -
    if($LASTEXITCODE-ne 0){throw "Final DB preservation gate failed."}

    @"
============================================================
SMART ORGANIZER PHASE 2C.3A PASS
============================================================
Transaction-aware GISLayer creation: ENABLED
Transaction-aware GISFeature ingestion: ENABLED
Existing GIS APIs changed: NO
Layer duplicate protection: CHECKSUM + ROLE
Feature duplicate protection: SOURCE ID / GEOMETRY HASH
Internal transaction behavior: FLUSH ONLY
Caller-owned commit/rollback: ENABLED
Live atomic rollback acceptance: PASS
Acceptance fixture persisted: NO
Migration: NONE
Sample-specific assumptions: NONE
Next gate: PHASE 2C.3B PERSISTENT IMPORT ALL ORCHESTRATOR
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
