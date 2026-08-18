
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================"
Write-Host "GeoPilot Urban Mainland Relocation Post-Verify V1.2"
Write-Host "READ-ONLY verification only - NO relocation rerun"
Write-Host "============================================================"
Write-Host ""

$PROJECT_ID = "f7617e94-7d8c-47d0-8bed-635cf2f48579"
$SITE_ID = "2ea1e98d-347c-4a0a-8e5b-5dd7f9553673"

Write-Host "[1/4] Confirming relocation is already committed..."
docker compose exec -T backend python -c @"
import uuid
from sqlalchemy import select
from app.db.session import get_session_factory
from app.models.site import Site
from app.models.raster import RasterDataset

pid=uuid.UUID('$PROJECT_ID')
sid=uuid.UUID('$SITE_ID')
s=get_session_factory()()
try:
    site=s.scalar(select(Site).where(Site.id==sid, Site.project_id==pid))
    rows=list(s.scalars(select(RasterDataset).where(
        RasterDataset.project_id==pid,
        RasterDataset.site_id==sid,
        RasterDataset.is_archived.is_(False)
    )))
    print('SITE_NAME=',site.name)
    print('GEOMETRY_REVISION=',site.geometry_revision)
    print('GEOMETRY=',site.geometry)
    print('RASTER_COUNT=',len(rows))
    for x in rows:
        print(x.name, x.bounds, x.checksum_sha256)
    assert site.geometry_revision==2
    assert '101.516093804939' in str(site.geometry)
    assert len(rows)==2
    assert all(abs(float(x.bounds['left'])-779670.0)<0.001 for x in rows)
finally:
    s.close()
"@
if ($LASTEXITCODE -ne 0) { throw "Committed relocation verification failed" }

Write-Host ""
Write-Host "[2/4] Readiness verification with dynamic owner resolution..."
docker compose exec -T backend python -c @"
import uuid
from sqlalchemy import select, inspect
from app.db.session import get_session_factory
from app.models.project import Project
from app.models.user import User
from app.services.track_b_acceptance import assess_track_b_readiness

pid=uuid.UUID('$PROJECT_ID')
s=get_session_factory()()
try:
    project=s.scalar(select(Project).where(Project.id==pid))
    if project is None:
        raise RuntimeError('Project not found')

    mapper=inspect(Project)
    owner_id=None
    owner_source=None

    for col in mapper.columns:
        for fk in col.foreign_keys:
            target=str(fk.target_fullname).lower()
            if target.endswith('users.id'):
                value=getattr(project,col.key,None)
                if value is not None:
                    owner_id=value
                    owner_source=col.key
                    break
        if owner_id is not None:
            break

    owner=None
    if owner_id is not None:
        owner=s.scalar(select(User).where(User.id==owner_id))
    else:
        for rel in mapper.relationships:
            if rel.mapper.class_ is User:
                value=getattr(project,rel.key,None)
                if value is not None:
                    owner=value
                    owner_source=rel.key
                    break

    if owner is None:
        raise RuntimeError('Unable to resolve Project owner from SQLAlchemy mapping')

    print('OWNER_SOURCE=',owner_source)
    print('OWNER_ID=',owner.id)

    result=assess_track_b_readiness(
        s,
        owner=owner,
        project_id=pid,
    )
    print('STATUS=',result['status'])
    print('URBAN_READY=',result['urban']['ready'])
    print('URBAN_SITE=',result['urban']['site_id'])
    print('RURAL_READY=',result['rural']['ready'])
    print('BLOCKERS=',result['blockers'])

    assert result['status']=='ready'
    assert result['urban']['ready'] is True
    assert str(result['urban']['site_id'])=='$SITE_ID'
    assert result['rural']['ready'] is True
    assert not result['blockers']
finally:
    s.close()
"@
if ($LASTEXITCODE -ne 0) { throw "Track B readiness verification failed" }

Write-Host ""
Write-Host "[3/4] Track B regression baseline..."
docker compose exec -e PYTHONPATH=/app -T backend pytest -q tests/test_track_b_hackathon.py
if ($LASTEXITCODE -ne 0) { throw "Track B regression failed" }

Write-Host ""
Write-Host "[4/4] Runtime health..."
docker compose ps

Write-Host ""
Write-Host "============================================================"
Write-Host "URBAN MAINLAND RELOCATION V1.2 POST-VERIFY PASS"
Write-Host "Relocation was already committed successfully."
Write-Host "Readiness + Track B regression remain green."
Write-Host "Now Ctrl+F5 and visually inspect the Urban map."
Write-Host "Do NOT run another Full Track B Mission yet."
Write-Host "============================================================"
