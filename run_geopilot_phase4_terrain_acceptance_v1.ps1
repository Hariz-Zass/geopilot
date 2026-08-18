
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================"
Write-Host "GeoPilot Phase 4 Terrain Acceptance V1"
Write-Host "Controlled synthetic DEM -> ingestion -> terrain.site_summary"
Write-Host "Track B source code is not modified"
Write-Host "============================================================"
Write-Host ""

$DEM = ".\urban_shah_alam_demo_dem.tif"
if (-not (Test-Path $DEM)) {
    throw "urban_shah_alam_demo_dem.tif not found in geopilot_v7 root."
}

$PROJECT_ID = "f7617e94-7d8c-47d0-8bed-635cf2f48579"
$SITE_ID = "2ea1e98d-347c-4a0a-8e5b-5dd7f9553673"

Write-Host "[1/6] Preflight: route/tool/site + no existing active DEM..."
docker compose exec -T backend python -c @"
import uuid
from sqlalchemy import select, inspect
from app.db.session import get_session_factory
from app.models.project import Project
from app.models.raster import RasterDataset
from app.models.site import Site
from app.services.data_requirement_router import route_question
from app.services.planning_tools import get_tool

pid=uuid.UUID('$PROJECT_ID'); sid=uuid.UUID('$SITE_ID')
s=get_session_factory()()
try:
    site=s.scalar(select(Site).where(Site.id==sid,Site.project_id==pid))
    assert site is not None
    print('SITE=',site.name)
    print('REVISION=',site.geometry_revision)
    print('GEOMETRY=',site.geometry)
    assert site.geometry_revision==2
    assert '101.516093804939' in str(site.geometry)

    rows=list(s.scalars(select(RasterDataset).where(
        RasterDataset.project_id==pid,
        RasterDataset.site_id==sid,
        RasterDataset.status=='ready',
        RasterDataset.is_archived.is_(False)
    )))
    dems=[]
    for x in rows:
        p=x.provenance or {}
        role=str(p.get('data_role') or p.get('terrain_type') or '').casefold()
        bands={str(v).casefold() for v in (x.band_names or [])}
        if role in {'dem','elevation','terrain_dem','digital_elevation_model'} or bands & {'dem','elevation','elevation_m','height_m'}:
            dems.append(x)
    print('ACTIVE_DEM_COUNT=',len(dems))
    assert len(dems)==0

    r=route_question('berapa slope tertinggi di kawasan ini')
    print('ROUTE=',r.state,r.capability,list(r.tools))
    assert r.state=='planned' and r.capability=='terrain_measurement'
    t=get_tool('terrain.site_summary')
    print('TOOL=',t)
    assert t.deterministic and t.read_only
finally:
    s.close()
"@
if ($LASTEXITCODE -ne 0) { throw "Preflight failed" }

Write-Host ""
Write-Host "[2/6] Copying controlled DEM into backend temp space..."
docker compose cp "$DEM" backend:/tmp/urban_shah_alam_demo_dem.tif
if ($LASTEXITCODE -ne 0) { throw "DEM copy failed" }

Write-Host ""
Write-Host "[3/6] Ingesting DEM through terrain ingestion service..."
@'
import asyncio
import io
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select, inspect

from app.db.session import get_session_factory
from app.models.project import Project
from app.models.user import User
from app.services.terrain_ingestion import ingest_site_dem

PROJECT_ID = uuid.UUID("f7617e94-7d8c-47d0-8bed-635cf2f48579")
SITE_ID = uuid.UUID("2ea1e98d-347c-4a0a-8e5b-5dd7f9553673")
PATH = Path("/tmp/urban_shah_alam_demo_dem.tif")

s = get_session_factory()()
try:
    project = s.scalar(select(Project).where(Project.id == PROJECT_ID))
    if project is None:
        raise RuntimeError("Project not found")

    mapper = inspect(Project)
    owner = None
    for col in mapper.columns:
        for fk in col.foreign_keys:
            if str(fk.target_fullname).lower().endswith("users.id"):
                owner_id = getattr(project, col.key, None)
                if owner_id is not None:
                    owner = s.scalar(select(User).where(User.id == owner_id))
                    break
        if owner is not None:
            break

    if owner is None:
        for rel in mapper.relationships:
            if rel.mapper.class_ is User:
                value = getattr(project, rel.key, None)
                if value is not None:
                    owner = value
                    break

    if owner is None:
        raise RuntimeError("Unable to resolve project owner")

    payload = PATH.read_bytes()
    upload = UploadFile(
        file=io.BytesIO(payload),
        filename="urban_shah_alam_demo_dem.tif",
    )

    dataset = asyncio.run(
        ingest_site_dem(
            s,
            owner=owner,
            project_id=PROJECT_ID,
            site_id=SITE_ID,
            file=upload,
            name="Urban Shah Alam Controlled Demo DEM",
        )
    )

    print("DEM_DATASET_ID=", dataset.id)
    print("STATUS=", dataset.status)
    print("CRS=", dataset.crs)
    print("BANDS=", dataset.band_names)
    print("BOUNDS=", dataset.bounds)
    print("SOURCE_URI=", dataset.source_uri)
    print("PROVENANCE=", dataset.provenance)
finally:
    s.close()
'@ | docker compose exec -T backend python -
if ($LASTEXITCODE -ne 0) { throw "DEM ingestion failed" }

Write-Host ""
Write-Host "[4/6] Running deterministic terrain summary..."
@'
import uuid
from sqlalchemy import select, inspect

from app.db.session import get_session_factory
from app.models.project import Project
from app.models.user import User
from app.services.terrain_analysis import calculate_site_terrain_summary

PROJECT_ID = uuid.UUID("f7617e94-7d8c-47d0-8bed-635cf2f48579")
SITE_ID = uuid.UUID("2ea1e98d-347c-4a0a-8e5b-5dd7f9553673")

s = get_session_factory()()
try:
    project = s.scalar(select(Project).where(Project.id == PROJECT_ID))
    mapper = inspect(Project)
    owner = None
    for col in mapper.columns:
        for fk in col.foreign_keys:
            if str(fk.target_fullname).lower().endswith("users.id"):
                owner_id = getattr(project, col.key, None)
                if owner_id is not None:
                    owner = s.scalar(select(User).where(User.id == owner_id))
                    break
        if owner is not None:
            break
    if owner is None:
        for rel in mapper.relationships:
            if rel.mapper.class_ is User:
                value = getattr(project, rel.key, None)
                if value is not None:
                    owner = value
                    break
    if owner is None:
        raise RuntimeError("Unable to resolve project owner")

    result = calculate_site_terrain_summary(
        s,
        owner=owner,
        project_id=PROJECT_ID,
        site_id=SITE_ID,
    )

    print("TERRAIN_RESULT=", result)
    for key in (
        "minimum_elevation_m",
        "maximum_elevation_m",
        "mean_elevation_m",
        "minimum_slope_degrees",
        "maximum_slope_degrees",
        "mean_slope_degrees",
        "maximum_slope_location",
    ):
        if hasattr(result, key):
            print(f"{key}=", getattr(result, key))

    max_slope = getattr(result, "maximum_slope_degrees", None)
    if max_slope is not None:
        assert 13.0 <= float(max_slope) <= 15.5, max_slope
finally:
    s.close()
'@ | docker compose exec -T backend python -
if ($LASTEXITCODE -ne 0) { throw "Terrain analysis failed" }

Write-Host ""
Write-Host "[5/6] Regression protection..."
docker compose exec -e PYTHONPATH=/app -T backend pytest -q tests/test_terrain_analysis.py tests/test_data_requirement_router.py tests/test_track_b_hackathon.py
if ($LASTEXITCODE -ne 0) { throw "Regression suite failed" }

Write-Host ""
Write-Host "[6/6] Runtime health..."
docker compose ps

Write-Host ""
Write-Host "============================================================"
Write-Host "PHASE 4 TERRAIN ACCEPTANCE V1 PASS"
Write-Host "A project/site-scoped DEM is now registered for Shah Alam."
Write-Host "terrain.site_summary produced deterministic terrain evidence."
Write-Host "Next: test Planning Copilot with 'berapa slope tertinggi di kawasan ini'."
Write-Host "============================================================"
