$ErrorActionPreference="Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Phase 2C.3B Controlled Commit Acceptance"
Write-Host "REAL COMMIT -> VERIFY -> CLEANUP -> BASELINE RESTORE"
Write-Host "============================================================"

$root=(Get-Location).Path
$log=Join-Path $root "artifacts\smart_organizer_phase2c3b_controlled_commit_acceptance.txt"

Write-Host "[0] Preflight"
$pre=@'
from pathlib import Path
for p in (
    "/app/app/services/track_b_smart_import_all.py",
    "/app/app/services/track_b_smart_transactional_gis.py",
    "/app/app/services/track_b_smart_transactional_site.py",
):
    assert Path(p).exists(), p
print("phase2c3b_runtime=CONFIRMED")
'@
$pre | docker compose exec -T -w /app backend python -
if($LASTEXITCODE-ne 0){throw "Phase 2C.3B runtime missing."}

Write-Host "[1] Build tiny organizer fixture inside backend"
$fixture=@'
import json, pathlib, subprocess, zipfile, shutil
root=pathlib.Path("/tmp/phase2c3b_acceptance")
if root.exists():
    shutil.rmtree(root)
root.mkdir(parents=True)

geojson={
  "type":"FeatureCollection",
  "features":[
    {
      "type":"Feature",
      "id":"A1",
      "properties":{"landuse":"residential","fixture":True},
      "geometry":{
        "type":"Polygon",
        "coordinates":[[
          [101.5002,3.0502],
          [101.5040,3.0502],
          [101.5040,3.0540],
          [101.5002,3.0540],
          [101.5002,3.0502]
        ]]
      }
    },
    {
      "type":"Feature",
      "id":"A2",
      "properties":{"landuse":"commercial","fixture":True},
      "geometry":{
        "type":"Polygon",
        "coordinates":[[
          [101.5060,3.0560],
          [101.5090,3.0560],
          [101.5090,3.0590],
          [101.5060,3.0590],
          [101.5060,3.0560]
        ]]
      }
    },
    {
      "type":"Feature",
      "id":"OUTSIDE",
      "properties":{"landuse":"industrial","fixture":True},
      "geometry":{
        "type":"Polygon",
        "coordinates":[[
          [102.0000,4.0000],
          [102.0100,4.0000],
          [102.0100,4.0100],
          [102.0000,4.0100],
          [102.0000,4.0000]
        ]]
      }
    }
  ]
}
src=root/"fixture.geojson"
src.write_text(json.dumps(geojson),encoding="utf-8")

gpkg=root/"organizer_fixture.gpkg"
r=subprocess.run(
    ["ogr2ogr","-f","GPKG",str(gpkg),str(src),"-nln","LAND_USE_FIXTURE"],
    text=True,capture_output=True
)
assert r.returncode==0, r.stderr

zip_path=root/"organizer_fixture.zip"
with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as z:
    z.write(gpkg,gpkg.name)

print("fixture_zip=",zip_path)
print("fixture_gpkg=",gpkg)
'@
$fixture | docker compose exec -T -w /app backend python -
if($LASTEXITCODE-ne 0){throw "Fixture build failed."}

Write-Host "[2] Real persistent import + verification + cleanup"
$accept=@'
import asyncio, json, uuid
from fastapi import UploadFile
from sqlalchemy import select, func, text

from app.db import get_session_factory
from app.models.project import Project
from app.models.user import User
from app.models.site import Site
from app.models.gis_layer import GISLayer
from app.models.gis_feature import GISFeature
from app.services.track_b_smart_import_all import ImportAllRequest, execute_persistent_import_all

SITE_GEOMETRY={
    "type":"Polygon",
    "coordinates":[[
        [101.5000,3.0500],
        [101.5100,3.0500],
        [101.5100,3.0600],
        [101.5000,3.0600],
        [101.5000,3.0500]
    ]]
}

async def main():
    db=get_session_factory()()
    created_site_id=None
    created_layer_ids=[]
    project=None
    baseline_active={}
    baseline={}
    try:
        project=db.scalar(
            select(Project)
            .where(Project.is_archived.is_(False))
            .order_by(Project.created_at.asc())
        )
        assert project is not None, "No non-archived project available."
        owner=db.get(User,project.owner_id)
        assert owner is not None, "Project owner missing."

        baseline={
            "sites": db.scalar(select(func.count()).select_from(Site)),
            "layers": db.scalar(select(func.count()).select_from(GISLayer)),
            "features": db.scalar(select(func.count()).select_from(GISFeature)),
        }
        existing_sites=list(db.scalars(select(Site).where(Site.project_id==project.id)))
        baseline_active={str(s.id): bool(s.is_active) for s in existing_sites}

        fixture_name="PHASE2C3B COMMIT FIXTURE "+uuid.uuid4().hex[:8]

        with open("/tmp/phase2c3b_acceptance/organizer_fixture.zip","rb") as handle:
            upload=UploadFile(filename="organizer_fixture.zip",file=handle)
            result=await execute_persistent_import_all(
                db,
                owner=owner,
                project_id=project.id,
                files=[upload],
                request=ImportAllRequest(
                    site_name=fixture_name,
                    site_geometry=SITE_GEOMETRY,
                    site_source_ref="phase2c3b_controlled_commit_acceptance",
                    user_confirmed=True,
                    role_assignments={
                        "organizer_fixture:LAND_USE_FIXTURE":"land_use"
                    },
                    allow_invalid_geometry_skip=False,
                    execute_persistent=True,
                ),
            )

        assert result["status"]=="committed", result
        assert result["committed"] is True
        assert result["database_writes"] is True
        assert result["site_created"] is True
        assert result["layers_created"]==1, result
        assert result["features_created"]==2, result
        assert result["features_duplicates_skipped"]==0, result

        created_site_id=uuid.UUID(result["site_id"])
        created_layer_ids=[uuid.UUID(x["layer_id"]) for x in result["imported_layers"]]

        site=db.get(Site,created_site_id)
        assert site is not None and site.is_active and not site.is_archived

        layer=db.get(GISLayer,created_layer_ids[0])
        assert layer is not None
        assert layer.provenance.get("applicability_role")=="land_use"
        assert layer.provenance.get("competition_track")=="B"
        assert layer.provenance.get("confirmed_site_id")==str(created_site_id)

        feats=list(db.scalars(
            select(GISFeature).where(GISFeature.layer_id==layer.id)
        ))
        assert len(feats)==2
        ids=sorted(f.source_feature_id for f in feats)
        assert ids==["A1","A2"], ids

        # Re-run exact same package to verify duplicate/reuse behavior.
        with open("/tmp/phase2c3b_acceptance/organizer_fixture.zip","rb") as handle:
            upload=UploadFile(filename="organizer_fixture.zip",file=handle)
            rerun=await execute_persistent_import_all(
                db,
                owner=owner,
                project_id=project.id,
                files=[upload],
                request=ImportAllRequest(
                    site_name=fixture_name,
                    site_geometry=SITE_GEOMETRY,
                    site_source_ref="phase2c3b_controlled_commit_acceptance",
                    user_confirmed=True,
                    role_assignments={
                        "organizer_fixture:LAND_USE_FIXTURE":"land_use"
                    },
                    allow_invalid_geometry_skip=False,
                    execute_persistent=True,
                ),
            )

        assert rerun["status"]=="committed"
        assert rerun["site_created"] is False
        assert rerun["site_duplicate_reused"] is True
        assert rerun["layers_created"]==0
        assert rerun["layers_reused"]==1
        assert rerun["features_created"]==0
        assert rerun["features_duplicates_skipped"]==2

        print("=== CONTROLLED COMMIT RESULT ===")
        print("first_commit_status=PASS")
        print("site_created=1")
        print("layers_created=1")
        print("features_created=2")
        print("outside_feature_imported=0")
        print("planning_role_provenance=PASS")
        print("second_run_site_reused=PASS")
        print("second_run_layer_reused=PASS")
        print("second_run_feature_duplicates_skipped=2")

        # Cleanup committed acceptance records.
        # Layer delete cascades features.
        for layer_id in created_layer_ids:
            layer=db.get(GISLayer,layer_id)
            if layer is not None:
                db.delete(layer)
        site=db.get(Site,created_site_id)
        if site is not None:
            db.delete(site)

        # Restore prior active-site states exactly.
        for site_id, active in baseline_active.items():
            original=db.get(Site,uuid.UUID(site_id))
            if original is not None:
                original.is_active=active

        db.commit()

        after={
            "sites": db.scalar(select(func.count()).select_from(Site)),
            "layers": db.scalar(select(func.count()).select_from(GISLayer)),
            "features": db.scalar(select(func.count()).select_from(GISFeature)),
        }

        assert after==baseline, (baseline,after)

        restored=list(db.scalars(select(Site).where(Site.project_id==project.id)))
        restored_active={str(s.id): bool(s.is_active) for s in restored}
        for site_id, active in baseline_active.items():
            assert restored_active.get(site_id)==active

        fixture_sites=db.scalar(
            select(func.count()).select_from(Site).where(Site.name==fixture_name)
        )
        fixture_layers=db.scalar(
            select(func.count()).select_from(GISLayer).where(
                GISLayer.provenance["ingestion_method"].as_string()
                =="smart_organizer_phase2c3b_import_all"
            )
        )

        print("")
        print("=== CLEANUP RESULT ===")
        print("baseline_sites=",baseline["sites"])
        print("baseline_layers=",baseline["layers"])
        print("baseline_features=",baseline["features"])
        print("after_sites=",after["sites"])
        print("after_layers=",after["layers"])
        print("after_features=",after["features"])
        print("active_site_state_restored=PASS")
        print("acceptance_fixture_site_count=",fixture_sites)
        print("controlled_commit_acceptance=PASS")
    except Exception:
        db.rollback()
        # best-effort cleanup if verification failed after first commit
        try:
            if created_layer_ids:
                for layer_id in created_layer_ids:
                    layer=db.get(GISLayer,layer_id)
                    if layer is not None:
                        db.delete(layer)
            if created_site_id:
                site=db.get(Site,created_site_id)
                if site is not None:
                    db.delete(site)
            for site_id, active in baseline_active.items():
                original=db.get(Site,uuid.UUID(site_id))
                if original is not None:
                    original.is_active=active
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()

asyncio.run(main())
'@

$accept 2>&1 |
docker compose exec -T -w /app backend python - 2>&1 |
Tee-Object -FilePath $log

if($LASTEXITCODE-ne 0){
    throw "Controlled commit acceptance failed. Send the log to ChatGPT; do not retry blindly."
}

Write-Host "[3] Final DB safety check"
$db=@'
from app.db import get_session_factory
from sqlalchemy import text
with get_session_factory()() as db:
    print("alembic_revision=",db.execute(text("SELECT version_num FROM alembic_version")).scalar())
    print("site_count=",db.execute(text("SELECT COUNT(*) FROM sites")).scalar())
    print("gis_layers=",db.execute(text("SELECT COUNT(*) FROM gis_layers")).scalar())
    print("gis_features=",db.execute(text("SELECT COUNT(*) FROM gis_features")).scalar())
    print("acceptance_site_count=",db.execute(text("SELECT COUNT(*) FROM sites WHERE name LIKE 'PHASE2C3B COMMIT FIXTURE %'")).scalar())
'@
$db | docker compose exec -T -w /app backend python - 2>&1 | Tee-Object -FilePath $log -Append
if($LASTEXITCODE-ne 0){throw "Final DB safety verification failed."}

Write-Host ""
Write-Host "============================================================"
Write-Host "CONTROLLED COMMIT ACCEPTANCE COMPLETE"
Write-Host "RESULT SAVED TO:"
Write-Host $log
Write-Host "============================================================"
