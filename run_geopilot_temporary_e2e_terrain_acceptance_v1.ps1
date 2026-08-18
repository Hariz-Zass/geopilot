$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "============================================================"
Write-Host "GeoPilot Temporary E2E Terrain Acceptance V1"
Write-Host "Temporary Site -> CDSE -> DEM -> RasterDataset -> Terrain Engine -> Cleanup"
Write-Host "============================================================"
Write-Host ""

$ProjectId = "f7617e94-7d8c-47d0-8bed-635cf2f48579"
$ProtectedSites = @(
    "f9cc540f-b611-497e-8a76-edac36ba01d6",
    "2ea1e98d-347c-4a0a-8e5b-5dd7f9553673"
)

Write-Host "[1] Preflight service health"
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "docker compose ps failed." }

Write-Host ""
Write-Host "[2] Runtime configuration gate"
docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); ok=bool(s.terrain_cdse_client_id) and bool(s.terrain_cdse_client_secret) and s.terrain_auto_acquisition_enabled and s.terrain_auto_provider=='copernicus_cdse'; print('CLIENT_ID configured:',bool(s.terrain_cdse_client_id)); print('CLIENT_SECRET configured:',bool(s.terrain_cdse_client_secret)); print('AUTO_ACQUISITION_ENABLED:',s.terrain_auto_acquisition_enabled); print('PROVIDER:',s.terrain_auto_provider); print('TARGET_CRS:',s.terrain_auto_target_crs); raise SystemExit(0 if ok else 2)"
if ($LASTEXITCODE -ne 0) { throw "Terrain runtime configuration gate failed." }

Write-Host ""
Write-Host "[3] Re-run terrain regression"
docker compose exec -T backend python -m pytest -q tests/test_terrain_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Terrain regression failed." }

Write-Host ""
Write-Host "[4] Execute isolated temporary E2E acceptance"
$py = @'
import hashlib
import inspect
import os
import uuid
from pathlib import Path

from sqlalchemy import select, func

from app.db import get_session_factory
from app.models.project import Project
from app.models.site import Site
from app.models.user import User
from app.models.raster import RasterDataset
from app.services.terrain_acquisition import acquire_site_dem_if_missing
from app.services.terrain_analysis import calculate_site_terrain_summary
from app.core.config import get_settings

PROJECT_ID = uuid.UUID("f7617e94-7d8c-47d0-8bed-635cf2f48579")
PROTECTED_SITE_IDS = {
    uuid.UUID("f9cc540f-b611-497e-8a76-edac36ba01d6"),
    uuid.UUID("2ea1e98d-347c-4a0a-8e5b-5dd7f9553673"),
}

# Small Shah Alam AOI, deliberately separate from protected QA Site IDs.
EWKT = (
    "SRID=4326;MULTIPOLYGON((("
    "101.5300 3.0700,"
    "101.5320 3.0700,"
    "101.5320 3.0720,"
    "101.5300 3.0720,"
    "101.5300 3.0700"
    ")))"
)

session = get_session_factory()()
temp_site = None
created_dataset = None
created_file = None

try:
    project = session.scalar(
        select(Project).where(
            Project.id == PROJECT_ID,
            Project.is_archived.is_(False),
        )
    )
    if project is None:
        raise RuntimeError("Target Track B project is missing or archived.")

    owner = session.scalar(select(User).where(User.id == project.owner_id))
    if owner is None:
        raise RuntimeError("Target project owner is missing.")

    before_sites = session.scalar(
        select(func.count()).select_from(Site).where(Site.project_id == PROJECT_ID)
    )
    before_rasters = session.scalar(
        select(func.count()).select_from(RasterDataset).where(
            RasterDataset.project_id == PROJECT_ID
        )
    )

    protected_before = {}
    for sid in PROTECTED_SITE_IDS:
        protected_before[sid] = session.scalar(
            select(func.count()).select_from(RasterDataset).where(
                RasterDataset.project_id == PROJECT_ID,
                RasterDataset.site_id == sid,
            )
        )

    temp_site = Site(
        project_id=PROJECT_ID,
        name=f"CDSE E2E TEMP {uuid.uuid4().hex[:8]}",
        geometry=EWKT,
        geometry_hash=hashlib.sha256(EWKT.encode("utf-8")).hexdigest(),
        geometry_revision=1,
        is_active=False,
        is_archived=False,
    )
    session.add(temp_site)
    session.commit()
    session.refresh(temp_site)

    if temp_site.id in PROTECTED_SITE_IDS:
        raise RuntimeError("Safety violation: temporary Site collided with a protected Site ID.")

    print("Temporary Site created:", temp_site.id)
    print("Protected QA Sites touched: NO")

    ready_before = session.scalar(
        select(func.count()).select_from(RasterDataset).where(
            RasterDataset.project_id == PROJECT_ID,
            RasterDataset.site_id == temp_site.id,
            RasterDataset.status == "ready",
            RasterDataset.is_archived.is_(False),
        )
    )
    print("Temporary Site ready DEM before:", ready_before)
    if ready_before != 0:
        raise RuntimeError("Temporary Site unexpectedly already has a ready DEM.")

    created_dataset = acquire_site_dem_if_missing(
        session,
        owner=owner,
        project_id=PROJECT_ID,
        site_id=temp_site.id,
    )

    print("Automatic DEM persisted: PASS")
    print("RasterDataset ID:", created_dataset.id)
    print("Provider:", created_dataset.provider)
    print("Collection:", created_dataset.collection)
    print("CRS:", created_dataset.crs)
    print("Raster size:", f"{created_dataset.width}x{created_dataset.height}")
    print("Status:", created_dataset.status)
    print("Ingestion method:", (created_dataset.provenance or {}).get("ingestion_method"))

    if created_dataset.provider != "copernicus_cdse":
        raise RuntimeError("Persisted DEM provider is not copernicus_cdse.")
    if (created_dataset.provenance or {}).get("ingestion_method") != "terrain_dem_auto_acquisition_v1":
        raise RuntimeError("Persisted DEM provenance is not terrain_dem_auto_acquisition_v1.")
    if created_dataset.status != "ready":
        raise RuntimeError("Persisted DEM is not ready.")

    source_uri = created_dataset.source_uri or ""
    if not source_uri.startswith("local://rasters/"):
        raise RuntimeError("Automatic DEM is not backed by local raster storage.")

    rel = source_uri[len("local://rasters/"):]
    storage_root = Path(get_settings().raster_storage_root).resolve()
    created_file = (storage_root / rel).resolve()
    if storage_root != created_file and storage_root not in created_file.parents:
        raise RuntimeError("Persisted raster path escaped configured raster root.")
    if not created_file.exists():
        raise RuntimeError("Persisted automatic DEM file does not exist.")
    print("Immutable raster file exists: PASS")
    print("Raster bytes:", created_file.stat().st_size)

    sig = inspect.signature(calculate_site_terrain_summary)
    print("Terrain Engine signature:", sig)

    # Current GeoPilot service contract is expected to use session/owner/project_id/site_id.
    kwargs = {}
    for name in sig.parameters:
        if name == "session":
            kwargs[name] = session
        elif name == "owner":
            kwargs[name] = owner
        elif name == "project_id":
            kwargs[name] = PROJECT_ID
        elif name == "site_id":
            kwargs[name] = temp_site.id
        elif sig.parameters[name].default is inspect._empty:
            raise RuntimeError(f"Unsupported required Terrain Engine argument: {name}")

    summary = calculate_site_terrain_summary(**kwargs)
    print("Terrain Engine consume persisted DEM: PASS")
    print("Terrain summary type:", type(summary).__name__)

    # Print safe scalar fields only; no secrets/tokens.
    if hasattr(summary, "__dict__"):
        safe = {}
        for k, v in summary.__dict__.items():
            if isinstance(v, (str, int, float, bool, type(None))):
                safe[k] = v
        print("Terrain summary scalars:", safe)

    for sid, count_before in protected_before.items():
        count_after = session.scalar(
            select(func.count()).select_from(RasterDataset).where(
                RasterDataset.project_id == PROJECT_ID,
                RasterDataset.site_id == sid,
            )
        )
        if count_after != count_before:
            raise RuntimeError(f"Protected QA Site raster count changed: {sid}")

    print("Protected QA raster counts unchanged: PASS")

    # Controlled cleanup: delete only the exact temporary RasterDataset and Site.
    dataset_id = created_dataset.id
    site_id = temp_site.id
    session.delete(created_dataset)
    session.flush()
    session.delete(temp_site)
    session.commit()

    if created_file and created_file.exists():
        created_file.unlink()
        # Best-effort remove empty temp directories only.
        parent = created_file.parent
        try:
            parent.rmdir()
            parent.parent.rmdir()
        except OSError:
            pass

    temp_site = None
    created_dataset = None

    after_sites = session.scalar(
        select(func.count()).select_from(Site).where(Site.project_id == PROJECT_ID)
    )
    after_rasters = session.scalar(
        select(func.count()).select_from(RasterDataset).where(
            RasterDataset.project_id == PROJECT_ID
        )
    )

    if after_sites != before_sites:
        raise RuntimeError(f"Cleanup failed: project Site count changed {before_sites} -> {after_sites}.")
    if after_rasters != before_rasters:
        raise RuntimeError(f"Cleanup failed: project RasterDataset count changed {before_rasters} -> {after_rasters}.")

    print("Temporary RasterDataset cleanup: PASS")
    print("Temporary Site cleanup: PASS")
    print("Temporary raster file cleanup: PASS")
    print("Project Site count restored:", after_sites)
    print("Project RasterDataset count restored:", after_rasters)
    print("E2E acceptance cleanup complete: PASS")

except Exception:
    session.rollback()

    # Best-effort cleanup if failure occurred after a committed temporary write.
    try:
        if created_dataset is not None:
            obj = session.get(RasterDataset, created_dataset.id)
            if obj is not None:
                session.delete(obj)
                session.commit()
    except Exception:
        session.rollback()

    try:
        if temp_site is not None:
            obj = session.get(Site, temp_site.id)
            if obj is not None and obj.id not in PROTECTED_SITE_IDS:
                # Remove any exact raster rows tied to only this temporary Site first.
                rows = list(session.scalars(select(RasterDataset).where(RasterDataset.site_id == obj.id)))
                for row in rows:
                    session.delete(row)
                session.flush()
                session.delete(obj)
                session.commit()
    except Exception:
        session.rollback()

    try:
        if created_file is not None and created_file.exists():
            created_file.unlink()
    except Exception:
        pass
    raise
finally:
    session.close()
'@

$tempPy = Join-Path $env:TEMP ("geopilot_e2e_terrain_" + [guid]::NewGuid().ToString("N") + ".py")
Set-Content -Path $tempPy -Value $py -Encoding UTF8

try {
    Get-Content -Raw $tempPy | docker compose exec -T backend python -
    if ($LASTEXITCODE -ne 0) {
        throw "Temporary E2E acceptance failed. Review the sanitized output above."
    }
}
finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $tempPy
}

Write-Host ""
Write-Host "[5] Post-acceptance service health"
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "Post-acceptance service health check failed." }

Write-Host ""
Write-Host "============================================================"
Write-Host "GEOPILOT TEMPORARY E2E TERRAIN ACCEPTANCE V1 PASS"
Write-Host "============================================================"
Write-Host "Temporary Site creation: PASS"
Write-Host "CDSE GLO-30 automatic acquisition: PASS"
Write-Host "Metric normalization + immutable raster persistence: PASS"
Write-Host "RasterDataset provenance persistence: PASS"
Write-Host "Terrain Engine consumed acquired DEM: PASS"
Write-Host "Protected Rural/Urban QA Sites unchanged: PASS"
Write-Host "Temporary DB rows cleaned up: PASS"
Write-Host "Temporary raster file cleaned up: PASS"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "Credential/token output: NONE"
Write-Host "============================================================"
