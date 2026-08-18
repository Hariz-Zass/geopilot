
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================"
Write-Host "GeoPilot Automatic Terrain Acquisition Foundation V1"
Write-Host "Provider-ready architecture + manual DEM precedence"
Write-Host "NO migration - NO frontend change - Track B protected"
Write-Host "============================================================"
Write-Host ""

$backup = ".\artifacts\auto_terrain_acquisition_v1_backup_$(Get-Date -Format yyyyMMdd_HHmmss)"
New-Item -ItemType Directory -Force -Path $backup | Out-Null

$files = @(
  ".\backend\app\core\config.py",
  ".\backend\app\services\terrain_analysis.py"
)
foreach ($f in $files) {
  if (Test-Path $f) { Copy-Item $f $backup -Force }
}
Write-Host "BACKUP: $backup"

Write-Host ""
Write-Host "[1/6] Applying controlled backend foundation patch..."

@'
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
import numpy as np
import rasterio
from pyproj import CRS
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_geom
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.raster import RasterDataset
from app.models.user import User
from app.schemas.site import ewkt_to_geojson
from app.services.isolation import (
    ProjectState,
    SiteState,
    resolve_project_scope,
    resolve_site_scope,
)


class TerrainAcquisitionError(Exception):
    pass


@dataclass(frozen=True)
class AcquiredTerrainArtifact:
    data: bytes
    provider: str
    collection: str
    scene_id: str
    acquisition_datetime: str | None
    source_reference: str
    original_crs: str
    metadata: dict


class TerrainProvider(Protocol):
    name: str

    def acquire(
        self,
        *,
        site_geometry: dict,
        target_crs: str,
    ) -> AcquiredTerrainArtifact:
        ...


def _terrain_role(dataset: RasterDataset) -> str | None:
    p = dataset.provenance or {}
    values = {
        str(v).strip().casefold()
        for v in (
            p.get("data_role"),
            p.get("terrain_type"),
            p.get("raster_role"),
            p.get("measurement"),
        )
        if v is not None
    }
    bands = {str(x).strip().casefold() for x in (dataset.band_names or [])}
    if values & {"dem", "elevation", "terrain_dem", "digital_elevation_model"}:
        return "elevation"
    if bands & {"dem", "elevation", "elevation_m", "height_m"}:
        return "elevation"
    return None


def ready_site_dems(
    session: Session,
    *,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> list[RasterDataset]:
    rows = list(
        session.scalars(
            select(RasterDataset).where(
                RasterDataset.project_id == project_id,
                RasterDataset.site_id == site_id,
                RasterDataset.status == "ready",
                RasterDataset.is_archived.is_(False),
            )
        )
    )
    return [x for x in rows if _terrain_role(x) == "elevation"]


def _evidence_priority(dataset: RasterDataset) -> tuple[int, object]:
    p = dataset.provenance or {}
    scope = str(p.get("evidence_scope") or "").casefold()
    method = str(p.get("ingestion_method") or "").casefold()
    provider = str(dataset.provider or "").casefold()

    if scope == "project_site_user_supplied" or provider == "user_supplied":
        rank = 0
    elif scope == "project_site_authoritative_acquired":
        rank = 10
    elif method == "terrain_dem_auto_acquisition_v1":
        rank = 20
    else:
        rank = 50

    return rank, dataset.created_at


def preferred_site_dem(
    session: Session,
    *,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> RasterDataset | None:
    candidates = ready_site_dems(
        session,
        project_id=project_id,
        site_id=site_id,
    )
    if not candidates:
        return None

    ranked = sorted(candidates, key=_evidence_priority)
    best_rank = _evidence_priority(ranked[0])[0]
    tied = [x for x in ranked if _evidence_priority(x)[0] == best_rank]

    if len(tied) > 1:
        raise TerrainAcquisitionError(
            "Multiple equally preferred DEM/elevation rasters exist for this Site; "
            "explicit DEM selection is required."
        )
    return ranked[0]


def _storage_root() -> Path:
    root = Path(get_settings().raster_storage_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_immutable(
    *,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    checksum: str,
    data: bytes,
) -> str:
    root = _storage_root()
    relative = Path(str(project_id)) / "terrain" / str(site_id) / f"{checksum}.tif"
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise TerrainAcquisitionError("Automatic DEM storage target escaped configured root.")
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            raise TerrainAcquisitionError("Existing automatic DEM artifact checksum mismatch.")
    else:
        temp = target.with_suffix(".tif.tmp")
        temp.write_bytes(data)
        os.replace(temp, target)

    return f"local://rasters/{relative.as_posix()}"


def _normalize_dem_to_metric_geotiff(
    data: bytes,
    *,
    target_crs: str,
) -> tuple[bytes, dict]:
    try:
        with MemoryFile(data) as src_mem:
            with src_mem.open() as src:
                if src.count < 1 or src.crs is None:
                    raise TerrainAcquisitionError("Provider DEM is missing a raster band or CRS.")

                target = CRS.from_user_input(target_crs)
                if not target.is_projected:
                    raise TerrainAcquisitionError("Automatic DEM target CRS must be projected.")

                transform, width, height = calculate_default_transform(
                    src.crs, target, src.width, src.height, *src.bounds
                )
                profile = src.profile.copy()
                profile.update(
                    driver="GTiff",
                    crs=target,
                    transform=transform,
                    width=width,
                    height=height,
                    count=1,
                    dtype="float32",
                    compress="deflate",
                )

                with MemoryFile() as dst_mem:
                    with dst_mem.open(**profile) as dst:
                        reproject(
                            source=rasterio.band(src, 1),
                            destination=rasterio.band(dst, 1),
                            src_transform=src.transform,
                            src_crs=src.crs,
                            dst_transform=transform,
                            dst_crs=target,
                            resampling=Resampling.bilinear,
                        )
                    normalized = dst_mem.read()

        with MemoryFile(normalized) as check_mem:
            with check_mem.open() as ds:
                meta = {
                    "crs": ds.crs.to_string(),
                    "width": ds.width,
                    "height": ds.height,
                    "pixel_size": {
                        "x": abs(float(ds.transform.a)),
                        "y": abs(float(ds.transform.e)),
                    },
                    "bounds": {
                        "left": float(ds.bounds.left),
                        "bottom": float(ds.bounds.bottom),
                        "right": float(ds.bounds.right),
                        "top": float(ds.bounds.top),
                    },
                    "nodata": {"values": list(ds.nodatavals)},
                    "driver": ds.driver,
                    "dtype": ds.dtypes[0],
                    "transform": tuple(ds.transform)[:6],
                }
        return normalized, meta
    except TerrainAcquisitionError:
        raise
    except Exception as exc:
        raise TerrainAcquisitionError("Provider DEM could not be normalized.") from exc


class CopernicusDemProvider:
    """
    Provider adapter boundary.

    V1 deliberately fails closed until CDSE credentials are configured.
    It does not silently scrape public endpoints or infer credentials.
    The next gate will bind this adapter to the official CDSE DEM process API.
    """

    name = "copernicus_cdse"

    def acquire(
        self,
        *,
        site_geometry: dict,
        target_crs: str,
    ) -> AcquiredTerrainArtifact:
        settings = get_settings()
        if not settings.terrain_cdse_client_id or not settings.terrain_cdse_client_secret:
            raise TerrainAcquisitionError(
                "Automatic Copernicus DEM acquisition is not configured. "
                "CDSE OAuth client credentials are required."
            )
        raise TerrainAcquisitionError(
            "Copernicus provider credentials are configured, but network acquisition "
            "is intentionally disabled until the provider acceptance gate is installed."
        )


def acquire_site_dem_if_missing(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    provider: TerrainProvider | None = None,
) -> RasterDataset:
    resolve_project_scope(
        session, owner=owner, project_id=project_id, state=ProjectState.ACTIVE
    )
    site_scope = resolve_site_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        project_state=ProjectState.ACTIVE,
        site_state=SiteState.AVAILABLE,
    )

    existing = preferred_site_dem(
        session,
        project_id=project_id,
        site_id=site_id,
    )
    if existing is not None:
        return existing

    settings = get_settings()
    if not settings.terrain_auto_acquisition_enabled:
        raise TerrainAcquisitionError(
            "No ready Site DEM is available and automatic terrain acquisition is disabled."
        )

    provider = provider or CopernicusDemProvider()
    site_geometry = ewkt_to_geojson(site_scope.site.geometry)

    artifact = provider.acquire(
        site_geometry=site_geometry,
        target_crs=settings.terrain_auto_target_crs,
    )

    normalized, inspected = _normalize_dem_to_metric_geotiff(
        artifact.data,
        target_crs=settings.terrain_auto_target_crs,
    )
    checksum = hashlib.sha256(normalized).hexdigest()
    source_uri = _write_immutable(
        project_id=project_id,
        site_id=site_id,
        checksum=checksum,
        data=normalized,
    )

    dataset = RasterDataset(
        project_id=project_id,
        site_id=site_id,
        created_by_user_id=owner.id,
        name=f"Automatic Terrain DEM - {artifact.provider}",
        source_kind="satellite_acquired",
        provider=artifact.provider,
        collection=artifact.collection,
        scene_id=artifact.scene_id,
        acquisition_datetime=artifact.acquisition_datetime,
        crs=inspected["crs"],
        width=inspected["width"],
        height=inspected["height"],
        band_count=1,
        band_names=["ELEVATION"],
        pixel_size=inspected["pixel_size"],
        bounds=inspected["bounds"],
        nodata=inspected["nodata"],
        source_uri=source_uri,
        checksum_sha256=checksum,
        provenance={
            "data_role": "dem",
            "terrain_type": "elevation",
            "vertical_measurement": "elevation",
            "vertical_unit": "metre",
            "evidence_scope": "project_site_authoritative_acquired",
            "ingestion_method": "terrain_dem_auto_acquisition_v1",
            "provider_source_reference": artifact.source_reference,
            "provider_original_crs": artifact.original_crs,
            "provider_metadata": artifact.metadata,
            "normalization": {
                "target_crs": settings.terrain_auto_target_crs,
                "driver": inspected["driver"],
                "dtype": inspected["dtype"],
                "transform": inspected["transform"],
            },
        },
        status="ready",
        is_archived=False,
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    return dataset
'@ | Set-Content ".\backend\app\services\terrain_acquisition.py" -Encoding UTF8

# Add config fields safely after raster settings.
$config = ".\backend\app\core\config.py"
$text = Get-Content $config -Raw
if ($text -notmatch "terrain_auto_acquisition_enabled") {
    $needle = '    raster_upload_max_bytes: int = Field(default=1073741824, ge=1048576, le=4294967296, alias="RASTER_UPLOAD_MAX_BYTES")'
    if (-not $text.Contains($needle)) {
        throw "Config insertion anchor not found; STOP."
    }
    $insert = @'
    raster_upload_max_bytes: int = Field(default=1073741824, ge=1048576, le=4294967296, alias="RASTER_UPLOAD_MAX_BYTES")
    terrain_auto_acquisition_enabled: bool = Field(default=False, alias="TERRAIN_AUTO_ACQUISITION_ENABLED")
    terrain_auto_provider: Literal["copernicus_cdse"] = Field(default="copernicus_cdse", alias="TERRAIN_AUTO_PROVIDER")
    terrain_auto_target_crs: str = Field(default="EPSG:32647", alias="TERRAIN_AUTO_TARGET_CRS")
    terrain_cdse_client_id: str | None = Field(default=None, alias="TERRAIN_CDSE_CLIENT_ID")
    terrain_cdse_client_secret: str | None = Field(default=None, alias="TERRAIN_CDSE_CLIENT_SECRET")
'@
    $text = $text.Replace($needle, $insert.TrimEnd())
    Set-Content $config $text -Encoding UTF8
    Write-Host "PATCHED: $config"
} else {
    Write-Host "CONFIG ALREADY PATCHED"
}

# Change DEM selection to deterministic precedence instead of rejecting manual+auto coexistence.
$analysis = ".\backend\app\services\terrain_analysis.py"
$a = Get-Content $analysis -Raw
if ($a -notmatch "preferred_site_dem") {
    $importNeedle = "from app.services.isolation import ("
    $a = $a.Replace(
        $importNeedle,
        "from app.services.terrain_acquisition import preferred_site_dem, TerrainAcquisitionError`r`nfrom app.services.isolation import ("
    )

    $start = $a.IndexOf("def select_site_dem(")
    $end = $a.IndexOf("`ndef _source_path(", $start)
    if ($start -lt 0 -or $end -lt 0) {
        throw "terrain_analysis select_site_dem block not found; STOP."
    }

    $replacement = @'
def select_site_dem(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> RasterDataset:
    resolve_project_scope(
        session, owner=owner, project_id=project_id, state=ProjectState.ACTIVE
    )
    resolve_site_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        project_state=ProjectState.ACTIVE,
        site_state=SiteState.AVAILABLE,
    )

    try:
        dataset = preferred_site_dem(
            session,
            project_id=project_id,
            site_id=site_id,
        )
    except TerrainAcquisitionError as exc:
        raise TerrainEvidenceMissing(str(exc)) from exc

    if dataset is None:
        raise TerrainEvidenceMissing(
            "No ready project/site-scoped DEM or elevation raster is available."
        )
    if not dataset.source_uri:
        raise TerrainEvidenceMissing(
            "The selected DEM/elevation raster has no readable source_uri."
        )
    return dataset

'@
    $a = $a.Substring(0, $start) + $replacement + $a.Substring($end + 1)
    Set-Content $analysis $a -Encoding UTF8
    Write-Host "PATCHED: $analysis"
} else {
    Write-Host "TERRAIN ANALYSIS ALREADY PATCHED"
}

@'
from __future__ import annotations

import uuid
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from sqlalchemy import select

from app.models.raster import RasterDataset
from app.services.terrain_acquisition import (
    AcquiredTerrainArtifact,
    acquire_site_dem_if_missing,
    preferred_site_dem,
)


class FakeProvider:
    name = "fake_authoritative"

    def __init__(self, data: bytes):
        self.data = data

    def acquire(self, *, site_geometry: dict, target_crs: str):
        return AcquiredTerrainArtifact(
            data=self.data,
            provider="fake_authoritative",
            collection="fake-dem-test",
            scene_id="fake-scene-001",
            acquisition_datetime=None,
            source_reference="test://fake-dem",
            original_crs=target_crs,
            metadata={"test": True},
        )


def test_manual_dem_precedence(session, owner, project, site):
    manual = RasterDataset(
        project_id=project.id,
        site_id=site.id,
        created_by_user_id=owner.id,
        name="Manual DEM",
        source_kind="upload",
        provider="user_supplied",
        collection="terrain-dem-v1",
        scene_id="manual",
        acquisition_datetime=None,
        crs="EPSG:32647",
        width=2,
        height=2,
        band_count=1,
        band_names=["ELEVATION"],
        pixel_size={"x": 10.0, "y": 10.0},
        bounds={"left": 0, "bottom": 0, "right": 20, "top": 20},
        nodata={"values": [None]},
        source_uri="local://rasters/manual.tif",
        checksum_sha256="a" * 64,
        provenance={
            "data_role": "dem",
            "terrain_type": "elevation",
            "evidence_scope": "project_site_user_supplied",
            "ingestion_method": "terrain_dem_upload_v1",
        },
        status="ready",
        is_archived=False,
    )
    auto = RasterDataset(
        project_id=project.id,
        site_id=site.id,
        created_by_user_id=owner.id,
        name="Auto DEM",
        source_kind="satellite_acquired",
        provider="copernicus_cdse",
        collection="copernicus-dem",
        scene_id="auto",
        acquisition_datetime=None,
        crs="EPSG:32647",
        width=2,
        height=2,
        band_count=1,
        band_names=["ELEVATION"],
        pixel_size={"x": 30.0, "y": 30.0},
        bounds={"left": 0, "bottom": 0, "right": 60, "top": 60},
        nodata={"values": [None]},
        source_uri="local://rasters/auto.tif",
        checksum_sha256="b" * 64,
        provenance={
            "data_role": "dem",
            "terrain_type": "elevation",
            "evidence_scope": "project_site_authoritative_acquired",
            "ingestion_method": "terrain_dem_auto_acquisition_v1",
        },
        status="ready",
        is_archived=False,
    )
    session.add_all([manual, auto])
    session.commit()
    selected = preferred_site_dem(session, project_id=project.id, site_id=site.id)
    assert selected.id == manual.id
'@ | Set-Content ".\backend\tests\test_terrain_acquisition.py" -Encoding UTF8

Write-Host ""
Write-Host "[2/6] Python compile gate..."
docker compose run --rm -e PYTHONPATH=/app backend python -m compileall `
  app/core/config.py `
  app/services/terrain_acquisition.py `
  app/services/terrain_analysis.py
if ($LASTEXITCODE -ne 0) { throw "Compile gate failed" }

Write-Host ""
Write-Host "[3/6] Existing terrain/router regression..."
docker compose run --rm -e PYTHONPATH=/app backend pytest -q `
  tests/test_terrain_analysis.py `
  tests/test_data_requirement_router.py
if ($LASTEXITCODE -ne 0) { throw "Terrain/router regression failed" }

Write-Host ""
Write-Host "[4/6] Track B regression protection..."
docker compose run --rm -e PYTHONPATH=/app backend pytest -q tests/test_track_b_hackathon.py
if ($LASTEXITCODE -ne 0) { throw "Track B regression failed" }

Write-Host ""
Write-Host "[5/6] Runtime precedence verification on current Shah Alam DEM..."
docker compose run --rm -e PYTHONPATH=/app backend python -c "import uuid; from sqlalchemy import select; from app.db.session import get_session_factory; from app.models.raster import RasterDataset; from app.services.terrain_acquisition import preferred_site_dem; s=get_session_factory()(); pid=uuid.UUID('f7617e94-7d8c-47d0-8bed-635cf2f48579'); sid=uuid.UUID('2ea1e98d-347c-4a0a-8e5b-5dd7f9553673'); d=preferred_site_dem(s,project_id=pid,site_id=sid); print('PREFERRED_DEM=',d.id,d.name,d.provider,(d.provenance or {}).get('evidence_scope')); s.close()"
if ($LASTEXITCODE -ne 0) { throw "Precedence verification failed" }

Write-Host ""
Write-Host "[6/6] Recreate backend + health..."
docker compose up -d --force-recreate backend
if ($LASTEXITCODE -ne 0) { throw "Backend recreate failed" }
docker compose ps backend db frontend

Write-Host ""
Write-Host "============================================================"
Write-Host "AUTO TERRAIN ACQUISITION FOUNDATION V1 PASS"
Write-Host "Manual/user DEM has deterministic priority."
Write-Host "Provider boundary + normalization + provenance path installed."
Write-Host "Copernicus network acquisition remains fail-closed until credentials/provider acceptance."
Write-Host "Track B remains regression-protected."
Write-Host "============================================================"
