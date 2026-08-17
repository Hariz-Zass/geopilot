from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.mask import mask
from rasterio.warp import transform_geom
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.raster import RasterDataset
from app.models.site import Site
from app.models.user import User
from app.services.terrain_acquisition import (
    acquire_site_dem_if_missing,
    preferred_site_dem,
    TerrainAcquisitionError,
)
from app.services.isolation import (
    ProjectState,
    SiteState,
    resolve_project_scope,
    resolve_site_scope,
)


class TerrainAnalysisError(Exception):
    pass


class TerrainEvidenceMissing(TerrainAnalysisError):
    pass


@dataclass(frozen=True)
class TerrainSummary:
    raster_id: uuid.UUID
    raster_checksum_sha256: str
    source_uri: str
    crs: str
    valid_pixel_count: int
    elevation_min_m: float
    elevation_max_m: float
    elevation_mean_m: float
    slope_min_degrees: float
    slope_max_degrees: float
    slope_mean_degrees: float
    max_slope_longitude: float
    max_slope_latitude: float


def _terrain_role(dataset: RasterDataset) -> str | None:
    p = dataset.provenance or {}
    candidates = [
        p.get("data_role"),
        p.get("terrain_type"),
        p.get("raster_role"),
        p.get("measurement"),
    ]
    normalized = {str(v).strip().casefold() for v in candidates if v is not None}
    if normalized & {"dem", "elevation", "terrain_dem", "digital_elevation_model"}:
        return "elevation"
    bands = {str(x).strip().casefold() for x in (dataset.band_names or [])}
    if bands & {"dem", "elevation", "elevation_m", "height_m"}:
        return "elevation"
    return None


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
        try:
            dataset = acquire_site_dem_if_missing(
                session,
                owner=owner,
                project_id=project_id,
                site_id=site_id,
            )
        except TerrainAcquisitionError as exc:
            raise TerrainEvidenceMissing(str(exc)) from exc
    if not dataset.source_uri:
        raise TerrainEvidenceMissing(
            "The selected DEM/elevation raster has no readable source_uri."
        )
    return dataset
def _source_path(source_uri: str) -> Path:
    value = source_uri.strip()
    if value.startswith("file://"):
        value = value[7:]
    elif value.startswith("local://"):
        rel = value[len("local://"):].lstrip("/")
        root = Path(get_settings().raster_storage_root)
        # local://rasters/foo.tif is rooted at the parent of RASTER_STORAGE_ROOT
        # when RASTER_STORAGE_ROOT itself is /data/rasters.
        if rel.startswith("rasters/") and root.name == "rasters":
            return root.parent / rel
        return root / rel
    elif "://" in value:
        raise TerrainEvidenceMissing(
            "Terrain Engine V1 accepts only local/file-backed DEM rasters."
        )
    path = Path(value)
    return path


def _metric_projected_crs(crs_value: str) -> CRS:
    crs = CRS.from_user_input(crs_value)
    if not crs.is_projected:
        raise TerrainEvidenceMissing(
            "Terrain Engine V1 requires a projected metric DEM CRS."
        )
    units = {str(axis.unit_name or "").casefold() for axis in crs.axis_info}
    if not any("metre" in u or "meter" in u for u in units):
        raise TerrainEvidenceMissing(
            "Terrain Engine V1 requires DEM horizontal units in metres."
        )
    return crs


def calculate_site_terrain_summary(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> TerrainSummary:
    dataset = select_site_dem(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
    )
    path = _source_path(dataset.source_uri or "")
    if not path.is_file():
        raise TerrainEvidenceMissing(
            "The selected DEM/elevation raster source file is not available."
        )

    site_scope = resolve_site_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        project_state=ProjectState.ACTIVE,
        site_state=SiteState.AVAILABLE,
    )
    site = site_scope.site

    ewkt = str(site.geometry)
    if ";" not in ewkt:
        raise TerrainAnalysisError("Site geometry is not valid EWKT.")
    wkt_text = ewkt.split(";", 1)[1]

    from shapely import wkt as shapely_wkt
    from shapely.geometry import mapping

    site_geom_4326 = mapping(shapely_wkt.loads(wkt_text))

    with rasterio.open(path) as ds:
        if ds.count < 1:
            raise TerrainEvidenceMissing("DEM raster contains no bands.")
        crs = _metric_projected_crs(str(ds.crs))
        geom = transform_geom("EPSG:4326", crs.to_string(), site_geom_4326)
        clipped, transform = mask(ds, [geom], crop=True, filled=False, indexes=1)
        elev = np.ma.asarray(clipped, dtype="float64")

        if elev.ndim != 2:
            raise TerrainAnalysisError("DEM clip did not produce a 2D elevation grid.")

        values = elev.compressed()
        values = values[np.isfinite(values)]
        if values.size < 4:
            raise TerrainEvidenceMissing(
                "DEM coverage within the Site is insufficient for terrain analysis."
            )

        filled = elev.filled(np.nan)
        valid = np.isfinite(filled)
        if np.count_nonzero(valid) < 4:
            raise TerrainEvidenceMissing("DEM has insufficient valid Site pixels.")

        # Gradient needs neighbouring values. Fill masked cells only for gradient
        # continuity, then restrict reported statistics back to originally valid cells.
        work = filled.copy()
        mean_fill = float(np.nanmean(work))
        work[~valid] = mean_fill

        dx = abs(float(transform.a))
        dy = abs(float(transform.e))
        if not (dx > 0 and dy > 0 and math.isfinite(dx) and math.isfinite(dy)):
            raise TerrainAnalysisError("DEM pixel size is invalid.")

        dz_dy, dz_dx = np.gradient(work, dy, dx)
        slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
        slope_valid = slope[valid]
        slope_valid = slope_valid[np.isfinite(slope_valid)]
        if slope_valid.size == 0:
            raise TerrainEvidenceMissing("No valid slope values were derived.")

        masked_slope = np.where(valid, slope, np.nan)
        flat_index = int(np.nanargmax(masked_slope))
        row, col = np.unravel_index(flat_index, masked_slope.shape)
        x, y = rasterio.transform.xy(transform, row, col, offset="center")
        to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        lon, lat = to_wgs84.transform(float(x), float(y))

    return TerrainSummary(
        raster_id=dataset.id,
        raster_checksum_sha256=dataset.checksum_sha256,
        source_uri=dataset.source_uri or "",
        crs=dataset.crs,
        valid_pixel_count=int(values.size),
        elevation_min_m=float(np.min(values)),
        elevation_max_m=float(np.max(values)),
        elevation_mean_m=float(np.mean(values)),
        slope_min_degrees=float(np.min(slope_valid)),
        slope_max_degrees=float(np.max(slope_valid)),
        slope_mean_degrees=float(np.mean(slope_valid)),
        max_slope_longitude=float(lon),
        max_slope_latitude=float(lat),
    )


