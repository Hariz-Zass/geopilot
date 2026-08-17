from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from fastapi import UploadFile
from pyproj import CRS
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.warp import transform_geom
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


class TerrainIngestionError(Exception):
    pass


@dataclass(frozen=True)
class InspectedDem:
    crs: str
    width: int
    height: int
    pixel_size: dict
    bounds: dict
    nodata: dict
    driver: str
    dtype: str
    transform: tuple[float, ...]
    valid_site_pixel_count: int


def _storage_root() -> Path:
    root = Path(get_settings().raster_storage_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _metric_projected_crs(crs_value: str) -> CRS:
    crs = CRS.from_user_input(crs_value)
    if not crs.is_projected:
        raise TerrainIngestionError(
            "DEM must use a projected CRS for deterministic slope measurement."
        )
    units = {str(axis.unit_name or "").casefold() for axis in crs.axis_info}
    if not any("metre" in u or "meter" in u for u in units):
        raise TerrainIngestionError("DEM horizontal CRS units must be metres.")
    return crs


def _inspect_dem_bytes(data: bytes, *, site_geometry: dict) -> InspectedDem:
    try:
        with MemoryFile(data) as mem:
            with mem.open() as ds:
                if ds.driver != "GTiff":
                    raise TerrainIngestionError(
                        "Terrain DEM ingestion accepts GeoTIFF only (.tif/.tiff)."
                    )
                if ds.crs is None:
                    raise TerrainIngestionError("DEM has no CRS.")
                _metric_projected_crs(ds.crs.to_string())
                if ds.count != 1:
                    raise TerrainIngestionError(
                        "Terrain Engine V1 requires a single-band elevation DEM."
                    )
                if ds.width <= 1 or ds.height <= 1:
                    raise TerrainIngestionError("DEM dimensions are insufficient.")
                if not np.issubdtype(np.dtype(ds.dtypes[0]), np.number):
                    raise TerrainIngestionError(
                        "DEM band must contain numeric elevation values."
                    )

                geom = transform_geom(
                    "EPSG:4326",
                    ds.crs.to_string(),
                    site_geometry,
                    precision=3,
                )
                clipped, _ = mask(
                    ds,
                    [geom],
                    crop=True,
                    filled=False,
                    indexes=1,
                )
                arr = np.ma.asarray(clipped, dtype="float64")
                values = arr.compressed()
                values = values[np.isfinite(values)]
                if values.size < 4:
                    raise TerrainIngestionError(
                        "DEM does not provide sufficient valid coverage inside the selected Site."
                    )

                dx = abs(float(ds.transform.a))
                dy = abs(float(ds.transform.e))
                if not (dx > 0 and dy > 0):
                    raise TerrainIngestionError("DEM pixel size is invalid.")

                return InspectedDem(
                    crs=ds.crs.to_string(),
                    width=ds.width,
                    height=ds.height,
                    pixel_size={"x": dx, "y": dy},
                    bounds={
                        "left": float(ds.bounds.left),
                        "bottom": float(ds.bounds.bottom),
                        "right": float(ds.bounds.right),
                        "top": float(ds.bounds.top),
                    },
                    nodata={"values": list(ds.nodatavals)},
                    driver=ds.driver,
                    dtype=ds.dtypes[0],
                    transform=tuple(ds.transform)[:6],
                    valid_site_pixel_count=int(values.size),
                )
    except TerrainIngestionError:
        raise
    except ValueError as exc:
        raise TerrainIngestionError(
            "DEM CRS or geometry could not be validated."
        ) from exc
    except Exception as exc:
        raise TerrainIngestionError(
            "Uploaded file is not a readable GeoTIFF DEM."
        ) from exc


def _write_immutable_dem(
    *,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    checksum: str,
    suffix: str,
    data: bytes,
) -> str:
    root = _storage_root()
    relative = (
        Path(str(project_id))
        / "terrain"
        / str(site_id)
        / f"{checksum}{suffix}"
    )
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise TerrainIngestionError("DEM storage target escaped configured root.")
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        existing = hashlib.sha256(target.read_bytes()).hexdigest()
        if existing != checksum:
            raise TerrainIngestionError("Existing DEM artifact checksum mismatch.")
    else:
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_bytes(data)
        os.replace(temp, target)

    return f"local://rasters/{relative.as_posix()}"


async def ingest_site_dem(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    file: UploadFile,
    name: str,
) -> RasterDataset:
    resolve_project_scope(
        session,
        owner=owner,
        project_id=project_id,
        state=ProjectState.ACTIVE,
    )
    site_scope = resolve_site_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        project_state=ProjectState.ACTIVE,
        site_state=SiteState.AVAILABLE,
    )

    filename = file.filename or ""
    suffix = Path(filename).suffix.casefold()
    if suffix not in {".tif", ".tiff"}:
        raise TerrainIngestionError(
            "DEM upload must be a GeoTIFF file with .tif or .tiff extension."
        )

    existing = list(
        session.scalars(
            select(RasterDataset).where(
                RasterDataset.project_id == project_id,
                RasterDataset.site_id == site_id,
                RasterDataset.status == "ready",
                RasterDataset.is_archived.is_(False),
            )
        )
    )
    for dataset in existing:
        p = dataset.provenance or {}
        role = str(p.get("data_role") or p.get("terrain_type") or "").casefold()
        bands = {str(x).casefold() for x in (dataset.band_names or [])}
        if role in {"dem", "elevation", "terrain_dem", "digital_elevation_model"} or (
            bands & {"dem", "elevation", "elevation_m", "height_m"}
        ):
            raise TerrainIngestionError(
                "A ready DEM/elevation raster already exists for this Site. "
                "Archive or explicitly replace it before uploading another DEM."
            )

    data = await file.read()
    settings = get_settings()
    if not data:
        raise TerrainIngestionError("DEM upload is empty.")
    if len(data) > settings.raster_upload_max_bytes:
        raise TerrainIngestionError(
            "DEM upload exceeds RASTER_UPLOAD_MAX_BYTES."
        )

    site_geometry = ewkt_to_geojson(site_scope.site.geometry)
    inspected = _inspect_dem_bytes(data, site_geometry=site_geometry)
    checksum = hashlib.sha256(data).hexdigest()
    source_uri = _write_immutable_dem(
        project_id=project_id,
        site_id=site_id,
        checksum=checksum,
        suffix=suffix,
        data=data,
    )

    dataset = RasterDataset(
        project_id=project_id,
        site_id=site_id,
        created_by_user_id=owner.id,
        name=" ".join(name.split()),
        source_kind="upload",
        provider="user_supplied",
        collection="terrain-dem-v1",
        scene_id=checksum[:16],
        acquisition_datetime=None,
        crs=inspected.crs,
        width=inspected.width,
        height=inspected.height,
        band_count=1,
        band_names=["ELEVATION"],
        pixel_size=inspected.pixel_size,
        bounds=inspected.bounds,
        nodata=inspected.nodata,
        source_uri=source_uri,
        checksum_sha256=checksum,
        provenance={
            "data_role": "dem",
            "terrain_type": "elevation",
            "vertical_measurement": "elevation",
            "vertical_unit": "metre",
            "evidence_scope": "project_site_user_supplied",
            "original_filename": filename,
            "driver": inspected.driver,
            "dtype": inspected.dtype,
            "transform": inspected.transform,
            "valid_site_pixel_count_at_ingestion": inspected.valid_site_pixel_count,
            "ingestion_method": "terrain_dem_upload_v1",
        },
        status="ready",
        is_archived=False,
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    return dataset
