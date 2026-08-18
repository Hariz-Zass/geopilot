$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "============================================================"
Write-Host "GeoPilot Normal API Terrain Acceptance V1"
Write-Host "API route -> auto CDSE -> persistence -> Terrain Engine -> cleanup"
Write-Host "============================================================"
Write-Host ""

Write-Host "[1] Preflight service health"
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "docker compose ps failed." }

Write-Host ""
Write-Host "[2] Terrain regression gate"
docker compose exec -T backend python -m pytest -q tests/test_terrain_analysis.py tests/test_terrain_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Terrain regression gate failed." }

Write-Host ""
Write-Host "[3] Execute normal authenticated API acceptance"

$py = @'
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
from sqlalchemy import select, func

from app.core.config import get_settings
from app.db import get_session_factory
from app.models.project import Project
from app.models.site import Site
from app.models.user import User
from app.models.raster import RasterDataset

PROJECT_ID = uuid.UUID("f7617e94-7d8c-47d0-8bed-635cf2f48579")
PROTECTED_SITE_IDS = {
    uuid.UUID("f9cc540f-b611-497e-8a76-edac36ba01d6"),
    uuid.UUID("2ea1e98d-347c-4a0a-8e5b-5dd7f9553673"),
}
EWKT = (
    "SRID=4326;MULTIPOLYGON((("
    "101.5400 3.0800,"
    "101.5420 3.0800,"
    "101.5420 3.0820,"
    "101.5400 3.0820,"
    "101.5400 3.0800"
    ")))"
)

settings = get_settings()
session = get_session_factory()()
temp_site_id = None
created_raster_id = None
created_file = None

try:
    project = session.scalar(
        select(Project).where(Project.id == PROJECT_ID, Project.is_archived.is_(False))
    )
    if project is None:
        raise RuntimeError("Target project missing or archived.")

    owner = session.scalar(select(User).where(User.id == project.owner_id))
    if owner is None or not owner.is_active:
        raise RuntimeError("Target project owner missing or inactive.")

    before_sites = session.scalar(
        select(func.count()).select_from(Site).where(Site.project_id == PROJECT_ID)
    )
    before_rasters = session.scalar(
        select(func.count()).select_from(RasterDataset).where(RasterDataset.project_id == PROJECT_ID)
    )
    protected_before = {
        sid: session.scalar(
            select(func.count()).select_from(RasterDataset).where(
                RasterDataset.project_id == PROJECT_ID,
                RasterDataset.site_id == sid,
            )
        )
        for sid in PROTECTED_SITE_IDS
    }

    site = Site(
        project_id=PROJECT_ID,
        name=f"API TERRAIN TEMP {uuid.uuid4().hex[:8]}",
        geometry=EWKT,
        geometry_hash=hashlib.sha256(EWKT.encode("utf-8")).hexdigest(),
        geometry_revision=1,
        is_active=False,
        is_archived=False,
    )
    session.add(site)
    session.commit()
    session.refresh(site)
    temp_site_id = site.id

    if temp_site_id in PROTECTED_SITE_IDS:
        raise RuntimeError("Safety violation: temporary Site collided with protected QA Site.")

    print("Temporary API Site created:", temp_site_id)
    print("Ready DEM before:", session.scalar(
        select(func.count()).select_from(RasterDataset).where(
            RasterDataset.project_id == PROJECT_ID,
            RasterDataset.site_id == temp_site_id,
            RasterDataset.status == "ready",
            RasterDataset.is_archived.is_(False),
        )
    ))

    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(owner.id),
            "iss": settings.auth_issuer,
            "iat": now,
            "exp": now + timedelta(minutes=10),
        },
        settings.auth_jwt_secret,
        algorithm=settings.auth_jwt_algorithm,
    )

    url = f"http://127.0.0.1:8000/api/v1/projects/{PROJECT_ID}/sites/{temp_site_id}/terrain/analysis"
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, headers={"Authorization": f"Bearer {token}"})

    print("API HTTP status:", response.status_code)
    if response.status_code != 200:
        try:
            print("API sanitized error:", response.json())
        except Exception:
            print("API sanitized error: non-JSON response")
        raise RuntimeError("Normal terrain analysis API did not return HTTP 200.")

    body = response.json()
    required = {
        "raster_id",
        "raster_checksum_sha256",
        "source_uri",
        "crs",
        "valid_pixel_count",
        "elevation_min_m",
        "elevation_max_m",
        "elevation_mean_m",
        "slope_min_degrees",
        "slope_max_degrees",
        "slope_mean_degrees",
        "max_slope_longitude",
        "max_slope_latitude",
    }
    missing = sorted(required - set(body))
    if missing:
        raise RuntimeError(f"API terrain response missing fields: {missing}")

    print("Normal API terrain analysis: PASS")
    print("API CRS:", body["crs"])
    print("API valid pixels:", body["valid_pixel_count"])
    print("API elevation min/max:", body["elevation_min_m"], body["elevation_max_m"])
    print("API slope mean:", body["slope_mean_degrees"])

    created_raster_id = uuid.UUID(body["raster_id"])
    session.expire_all()
    dataset = session.scalar(
        select(RasterDataset).where(
            RasterDataset.id == created_raster_id,
            RasterDataset.project_id == PROJECT_ID,
            RasterDataset.site_id == temp_site_id,
        )
    )
    if dataset is None:
        raise RuntimeError("API response raster_id was not persisted for temporary Site.")
    if dataset.provider != "copernicus_cdse":
        raise RuntimeError("API-acquired DEM provider is not copernicus_cdse.")
    if dataset.collection != "copernicus-dem-glo-30":
        raise RuntimeError("API-acquired DEM collection is not copernicus-dem-glo-30.")
    if (dataset.provenance or {}).get("ingestion_method") != "terrain_dem_auto_acquisition_v1":
        raise RuntimeError("API-acquired DEM provenance is incorrect.")
    if dataset.status != "ready":
        raise RuntimeError("API-acquired DEM is not ready.")

    print("RasterDataset persistence: PASS")
    print("Provider:", dataset.provider)
    print("Collection:", dataset.collection)
    print("Ingestion method:", (dataset.provenance or {}).get("ingestion_method"))

    source_uri = dataset.source_uri or ""
    if not source_uri.startswith("local://rasters/"):
        raise RuntimeError("API-acquired DEM is not local raster-backed.")
    rel = source_uri[len("local://rasters/"):]
    root = Path(settings.raster_storage_root).resolve()
    created_file = (root / rel).resolve()
    if root != created_file and root not in created_file.parents:
        raise RuntimeError("Automatic raster path escaped configured root.")
    if not created_file.exists():
        raise RuntimeError("API-acquired raster file is missing.")
    print("Immutable raster file: PASS")
    print("Raster bytes:", created_file.stat().st_size)

    for sid, count_before in protected_before.items():
        count_after = session.scalar(
            select(func.count()).select_from(RasterDataset).where(
                RasterDataset.project_id == PROJECT_ID,
                RasterDataset.site_id == sid,
            )
        )
        if count_after != count_before:
            raise RuntimeError(f"Protected QA Site raster count changed: {sid}")
    print("Protected QA Sites unchanged: PASS")

    # Exact controlled cleanup.
    session.delete(dataset)
    session.flush()
    temp_site = session.get(Site, temp_site_id)
    if temp_site is None or temp_site.id in PROTECTED_SITE_IDS:
        raise RuntimeError("Temporary Site cleanup safety check failed.")
    session.delete(temp_site)
    session.commit()

    if created_file.exists():
        created_file.unlink()
        parent = created_file.parent
        try:
            parent.rmdir()
            parent.parent.rmdir()
        except OSError:
            pass

    after_sites = session.scalar(
        select(func.count()).select_from(Site).where(Site.project_id == PROJECT_ID)
    )
    after_rasters = session.scalar(
        select(func.count()).select_from(RasterDataset).where(RasterDataset.project_id == PROJECT_ID)
    )
    if after_sites != before_sites:
        raise RuntimeError(f"Site count not restored: {before_sites} -> {after_sites}")
    if after_rasters != before_rasters:
        raise RuntimeError(f"RasterDataset count not restored: {before_rasters} -> {after_rasters}")

    temp_site_id = None
    created_raster_id = None
    print("Temporary DB cleanup: PASS")
    print("Temporary file cleanup: PASS")
    print("Project Site count restored:", after_sites)
    print("Project RasterDataset count restored:", after_rasters)
    print("NORMAL API E2E ACCEPTANCE: PASS")

except Exception:
    session.rollback()
    try:
        if created_raster_id is not None:
            obj = session.get(RasterDataset, created_raster_id)
            if obj is not None:
                if created_file is None and obj.source_uri and obj.source_uri.startswith("local://rasters/"):
                    rel = obj.source_uri[len("local://rasters/"):]
                    created_file = (Path(settings.raster_storage_root).resolve() / rel).resolve()
                session.delete(obj)
                session.commit()
    except Exception:
        session.rollback()
    try:
        if temp_site_id is not None and temp_site_id not in PROTECTED_SITE_IDS:
            rows = list(session.scalars(select(RasterDataset).where(RasterDataset.site_id == temp_site_id)))
            for row in rows:
                session.delete(row)
            session.flush()
            obj = session.get(Site, temp_site_id)
            if obj is not None:
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

$tempPy = Join-Path $env:TEMP ("geopilot_normal_api_terrain_" + [guid]::NewGuid().ToString("N") + ".py")
Set-Content -Path $tempPy -Value $py -Encoding UTF8
try {
    Get-Content -Raw $tempPy | docker compose exec -T backend python -
    if ($LASTEXITCODE -ne 0) { throw "Normal API terrain acceptance failed." }
}
finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $tempPy
}

Write-Host ""
Write-Host "[4] Post-acceptance service health"
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "Post-acceptance health check failed." }

Write-Host ""
Write-Host "============================================================"
Write-Host "GEOPILOT NORMAL API TERRAIN ACCEPTANCE V1 PASS"
Write-Host "============================================================"
Write-Host "Authenticated POST terrain/analysis: PASS"
Write-Host "Missing DEM triggered CDSE automatically: PASS"
Write-Host "RasterDataset + provenance persisted: PASS"
Write-Host "Terrain Engine response returned through API: PASS"
Write-Host "Protected Track B QA Sites unchanged: PASS"
Write-Host "Temporary DB rows/file cleaned: PASS"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "Credential/token output: NONE"
Write-Host "============================================================"
