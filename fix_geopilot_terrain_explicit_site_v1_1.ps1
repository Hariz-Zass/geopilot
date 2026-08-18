
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================"
Write-Host "GeoPilot Terrain Explicit-Site Fix V1.1"
Write-Host "Fixes terrain analysis rejecting a valid selected Site only"
Write-Host "No DEM re-upload - No Track B logic change"
Write-Host "============================================================"
Write-Host ""

$terrain = ".\backend\app\services\terrain_analysis.py"
if (-not (Test-Path $terrain)) { throw "terrain_analysis.py not found" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = ".\artifacts\terrain_explicit_site_fix_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $terrain "$backup\terrain_analysis.py"

Write-Host "[1/6] Applying exact explicit-site patch..."
$text = Get-Content $terrain -Raw

$old = @'
    site = session.scalar(
        select(Site).where(
            Site.id == site_id,
            Site.project_id == project_id,
            Site.is_active.is_(True),
            Site.is_archived.is_(False),
        )
    )
    if site is None:
        raise TerrainEvidenceMissing("Active Site geometry is unavailable.")
'@

$new = @'
    site_scope = resolve_site_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        project_state=ProjectState.ACTIVE,
        site_state=SiteState.AVAILABLE,
    )
    site = site_scope.site
'@

if (-not $text.Contains($old)) {
    throw "Expected terrain active-site block not found. STOP."
}

$text = $text.Replace($old, $new)
Set-Content -Path $terrain -Value $text -Encoding UTF8

Write-Host "BACKUP: $backup"
Write-Host "PATCHED: $terrain"

Write-Host ""
Write-Host "[2/6] Compile gate..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend backend python -m compileall app/services/terrain_analysis.py
if ($LASTEXITCODE -ne 0) { throw "Compile failed" }

Write-Host ""
Write-Host "[3/6] Terrain + router regression..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend backend pytest -q tests/test_terrain_analysis.py tests/test_data_requirement_router.py
if ($LASTEXITCODE -ne 0) { throw "Terrain/router tests failed" }

Write-Host ""
Write-Host "[4/6] Existing DEM deterministic acceptance..."
@'
import uuid
from sqlalchemy import select, inspect
from app.db.session import get_session_factory
from app.models.project import Project
from app.models.user import User
from app.services.terrain_analysis import calculate_site_terrain_summary

PROJECT_ID=uuid.UUID("f7617e94-7d8c-47d0-8bed-635cf2f48579")
SITE_ID=uuid.UUID("2ea1e98d-347c-4a0a-8e5b-5dd7f9553673")

s=get_session_factory()()
try:
    project=s.scalar(select(Project).where(Project.id==PROJECT_ID))
    mapper=inspect(Project)
    owner=None
    for col in mapper.columns:
        for fk in col.foreign_keys:
            if str(fk.target_fullname).lower().endswith("users.id"):
                owner_id=getattr(project,col.key,None)
                if owner_id is not None:
                    owner=s.scalar(select(User).where(User.id==owner_id))
                    break
        if owner is not None:
            break
    if owner is None:
        for rel in mapper.relationships:
            if rel.mapper.class_ is User:
                value=getattr(project,rel.key,None)
                if value is not None:
                    owner=value
                    break
    if owner is None:
        raise RuntimeError("Unable to resolve project owner")

    r=calculate_site_terrain_summary(
        s,
        owner=owner,
        project_id=PROJECT_ID,
        site_id=SITE_ID,
    )
    print("RASTER_ID=",r.raster_id)
    print("VALID_PIXELS=",r.valid_pixel_count)
    print("ELEVATION_MIN_M=",r.elevation_min_m)
    print("ELEVATION_MAX_M=",r.elevation_max_m)
    print("ELEVATION_MEAN_M=",r.elevation_mean_m)
    print("SLOPE_MIN_DEG=",r.slope_min_degrees)
    print("SLOPE_MAX_DEG=",r.slope_max_degrees)
    print("SLOPE_MEAN_DEG=",r.slope_mean_degrees)
    print("MAX_SLOPE_LON=",r.max_slope_longitude)
    print("MAX_SLOPE_LAT=",r.max_slope_latitude)
    assert r.valid_pixel_count > 1000
    assert 13.0 <= float(r.slope_max_degrees) <= 15.5
finally:
    s.close()
'@ | docker compose run --rm --no-deps -T -v "${PWD}:/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend backend python -
if ($LASTEXITCODE -ne 0) { throw "Deterministic terrain acceptance failed" }

Write-Host ""
Write-Host "[5/6] Track B regression protection..."
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend backend pytest -q tests/test_track_b_hackathon.py
if ($LASTEXITCODE -ne 0) { throw "Track B regression failed" }

Write-Host ""
Write-Host "[6/6] Recreate backend + runtime verification..."
docker compose up -d --force-recreate backend
if ($LASTEXITCODE -ne 0) { throw "Backend recreate failed" }

Start-Sleep -Seconds 4
docker compose exec -T backend python -c "from app.services.planning_tools import get_tool; print('TERRAIN_TOOL=',get_tool('terrain.site_summary'))"
if ($LASTEXITCODE -ne 0) { throw "Runtime verification failed" }

Write-Host ""
Write-Host "============================================================"
Write-Host "TERRAIN EXPLICIT-SITE FIX V1.1 PASS"
Write-Host "Existing Shah Alam DEM now works with the explicitly selected Site."
Write-Host "No DEM was re-uploaded."
Write-Host "Track B remains regression-protected."
Write-Host "============================================================"
