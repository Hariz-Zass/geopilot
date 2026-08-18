from __future__ import annotations
import asyncio, io, json, pathlib, shutil, subprocess, tempfile, traceback, uuid
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.inspection import inspect as sa_inspect
from app.db import get_session_factory
from app.models.gis_feature import GISFeature
from app.models.gis_layer import GISLayer
from app.models.planning_run import PlanningRun
from app.models.project import Project
from app.models.site import Site
from app.models.user import User
from app.schemas.planning_run import PlanningRunCreate
from app.services.planning_runs import create_planning_run
from app.services.planning_orchestrator import execute_planning_run
from app.services.planning_tools import execute_site_applicability
from app.services.track_b_smart_import_all import ImportAllRequest, execute_persistent_import_all
from app.services.isolation import SiteState

SITE_NAME="FINAL JUDGE DEMO AI ACCEPTANCE"
SOURCE_REF="final-judge-demo://temporary-acceptance"
LOGICAL_NAME="final_judge_land_use:FINAL_JUDGE_LAND_USE"
QUESTION="What land use applies to this site based only on the uploaded GIS layer? Use validated site applicability evidence only."

SITE_GEOMETRY={"type":"Polygon","coordinates":[[[101.7020,3.0010],[101.7100,3.0010],[101.7100,3.0050],[101.7020,3.0050],[101.7020,3.0010]]]}
FEATURE_COLLECTION={"type":"FeatureCollection","features":[
{"type":"Feature","id":"judge-residential","properties":{"fixture_key":"judge-residential","land_use":"Residential","acceptance_fixture":True},"geometry":{"type":"Polygon","coordinates":[[[101.7000,3.0000],[101.7060,3.0000],[101.7060,3.0060],[101.7000,3.0060],[101.7000,3.0000]]]}},
{"type":"Feature","id":"judge-commercial","properties":{"fixture_key":"judge-commercial","land_use":"Commercial","acceptance_fixture":True},"geometry":{"type":"Polygon","coordinates":[[[101.7060,3.0000],[101.7120,3.0000],[101.7120,3.0060],[101.7060,3.0060],[101.7060,3.0000]]]}}
]}

def counts(s):
    return {
        "sites": s.scalar(select(func.count()).select_from(Site)),
        "layers": s.scalar(select(func.count()).select_from(GISLayer)),
        "features": s.scalar(select(func.count()).select_from(GISFeature)),
        "planning_runs": s.scalar(select(func.count()).select_from(PlanningRun)),
    }

def build_gpkg():
    root=pathlib.Path(tempfile.mkdtemp(prefix="geopilot_final_judge_"))
    src=root/"final_judge_land_use.geojson"
    gpkg=root/"final_judge_land_use.gpkg"
    src.write_text(json.dumps(FEATURE_COLLECTION),encoding="utf-8")
    p=subprocess.run(["ogr2ogr","-f","GPKG",str(gpkg),str(src),"-nln","FINAL_JUDGE_LAND_USE"],text=True,capture_output=True)
    print("ogr2ogr_exit =",p.returncode)
    if p.stdout.strip(): print("ogr2ogr_stdout =",p.stdout.strip())
    if p.stderr.strip(): print("ogr2ogr_stderr =",p.stderr.strip())
    if p.returncode!=0 or not gpkg.exists(): raise RuntimeError("Unable to build GeoPackage fixture.")
    return root,gpkg

def serialize_model(obj):
    out={}
    for c in sa_inspect(obj.__class__).columns:
        v=getattr(obj,c.key)
        out[c.key]=str(v) if isinstance(v,uuid.UUID) else v
    return out

async def main():
    s=get_session_factory()()
    fixture_root=None
    created_site_id=None
    planning_run_id=None
    baseline=None
    try:
        print("="*72)
        print("GEOPILOT FINAL JUDGE DEMO ACCEPTANCE")
        print("SMART ORGANIZER GIS -> PLANNING OFFICER GROUNDED CONSUMPTION")
        print("="*72)

        project=s.scalar(select(Project).where(Project.is_archived.is_(False)).order_by(Project.created_at.asc()))
        if project is None: raise RuntimeError("No non-archived project found.")
        owner=s.get(User,project.owner_id)
        if owner is None: raise RuntimeError("Project owner not found.")
        print("owner_id =",owner.id)
        print("project_id =",project.id)

        baseline=counts(s)
        print("BASELINE =",baseline)
        if baseline["layers"]!=0 or baseline["features"]!=0:
            raise RuntimeError("Baseline GIS is not empty. STOP.")

        print("\n[A] BUILD TEMPORARY GPKG FIXTURE")
        fixture_root,gpkg=build_gpkg()

        print("\n[B] SMART ORGANIZER PERSISTENT IMPORT")
        with gpkg.open("rb") as h:
            upload=UploadFile(filename="final_judge_land_use.gpkg",file=h)
            req=ImportAllRequest(
                site_name=SITE_NAME,
                site_geometry=SITE_GEOMETRY,
                site_source_ref=SOURCE_REF,
                user_confirmed=True,
                role_assignments={LOGICAL_NAME:"land_use"},
                allow_invalid_geometry_skip=False,
                execute_persistent=True,
            )
            result=await execute_persistent_import_all(s,owner=owner,project_id=project.id,files=[upload],request=req)

        print("IMPORT_RESULT =",result)
        if result.get("status")!="committed":
            raise RuntimeError(f"Smart Organizer import did not commit: {result}")
        created_site_id=uuid.UUID(result["site_id"])
        imported=result.get("imported_layers",[])
        if len(imported)!=1: raise RuntimeError("Expected one imported layer.")
        layer_id=uuid.UUID(imported[0]["layer_id"])

        feats=list(s.scalars(select(GISFeature).where(
            GISFeature.project_id==project.id,
            GISFeature.layer_id==layer_id,
            GISFeature.is_archived.is_(False)
        ).order_by(GISFeature.created_at.asc(),GISFeature.id.asc())))
        if len(feats)!=2: raise RuntimeError(f"Expected 2 GIS features, got {len(feats)}")
        print("SMART_ORGANIZER_IMPORT = PASS")
        print("feature_count =",len(feats))

        print("\n[C] DETERMINISTIC SITE APPLICABILITY")
        ev,limits=execute_site_applicability(
            s,owner=owner,project_id=project.id,site_id=created_site_id,site_state=SiteState.AVAILABLE
        )
        print("spatial_evidence_count =",len(ev))
        print("spatial_limitations =",limits)
        evtext=json.dumps([x.model_dump(mode="json") if hasattr(x,"model_dump") else str(x) for x in ev],default=str).casefold()
        if len(ev)!=2 or "residential" not in evtext or "commercial" not in evtext:
            raise RuntimeError("Site applicability evidence is incomplete.")
        print("SITE_APPLICABILITY_EVIDENCE = PASS")

        print("\n[D] PLANNING OFFICER GROUNDED RUN")
        print("QUESTION =",QUESTION)
        run=create_planning_run(
            s,owner=owner,project_id=project.id,site_id=created_site_id,
            request=PlanningRunCreate(question=QUESTION,development_intent=None),
            site_state=SiteState.AVAILABLE
        )
        planning_run_id=run.id
        executed=execute_planning_run(
            s,owner=owner,project_id=project.id,site_id=created_site_id,
            run_id=planning_run_id,site_state=SiteState.AVAILABLE
        )
        s.refresh(executed)
        row=serialize_model(executed)
        print("PLANNING_RUN_ROW =",json.dumps(row,ensure_ascii=False,default=str))
        searchable=json.dumps(row,ensure_ascii=False,default=str).casefold()
        markers=[m for m in ("gis.site_applicability","site_applicability","residential","commercial") if m in searchable]
        print("GROUNDING_MARKERS_FOUND =",markers)
        if not any(m in searchable for m in ("gis.site_applicability","site_applicability")):
            raise RuntimeError("Planning run lacks site applicability grounding marker.")
        if "residential" not in searchable or "commercial" not in searchable:
            raise RuntimeError("Planning run did not preserve both validated land-use facts.")
        status=str(row.get("status","")).casefold()
        print("planning_run_status =",status or "<not-exposed>")
        if status in {"failed","error","blocked"}:
            raise RuntimeError(f"Planning run ended with status {status}")
        print("PLANNING_OFFICER_GROUNDED_CONSUMPTION = PASS")

        print("\n"+"="*72)
        print("FINAL_JUDGE_DEMO_ACCEPTANCE = PASS")
        print("SMART ORGANIZER -> GIS -> PLANNING OFFICER = PROVEN")
        print("="*72)

    except Exception:
        print("\n"+"="*72)
        print("FINAL_JUDGE_DEMO_ACCEPTANCE = ERROR/BLOCKED")
        print("="*72)
        traceback.print_exc()
        raise

    finally:
        print("\n[E] CONTROLLED CLEANUP")
        cleanup_error=None
        try:
            s.rollback()

            if planning_run_id is not None:
                r=s.get(PlanningRun,planning_run_id)
                if r is not None:
                    s.delete(r)
                    s.flush()

            layers=list(s.scalars(select(GISLayer).where(
                GISLayer.provenance["site_source_ref"].as_string()==SOURCE_REF
            )))
            for layer in layers: s.delete(layer)
            s.flush()

            sites=list(s.scalars(select(Site).where(Site.name==SITE_NAME)))
            for site in sites: s.delete(site)
            s.commit()

            after=counts(s)
            print("AFTER_CLEANUP =",after)
            if baseline is not None and after!=baseline:
                raise RuntimeError(f"Cleanup did not restore baseline: before={baseline}, after={after}")
            print("FINAL_JUDGE_CLEANUP = PASS")
        except Exception as exc:
            s.rollback()
            cleanup_error=exc
            print("FINAL_JUDGE_CLEANUP = FAILED")
            traceback.print_exc()
        finally:
            s.close()
            if fixture_root is not None and fixture_root.exists():
                shutil.rmtree(fixture_root,ignore_errors=True)
        if cleanup_error is not None: raise cleanup_error

if __name__=="__main__":
    asyncio.run(main())
