from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import rasterio
from fastapi import UploadFile
from pyproj import CRS, Geod
from rasterio.enums import Resampling
from rasterio.features import geometry_mask, shapes
from rasterio.io import MemoryFile
from rasterio.warp import reproject, transform_bounds, transform_geom
from shapely.geometry import shape, mapping
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.raster import RasterDataset
from app.models.user import User
from app.schemas.track_b import TrackBAnalysisRequest
from app.schemas.site import SiteCreateRequest, ewkt_to_geojson
from app.services.sites import create_site
from app.services.isolation import ProjectState, SiteState, resolve_project_scope, resolve_site_scope
from app.services.rasters import RasterError, get_raster


class TrackBError(Exception):
    pass


@dataclass(frozen=True)
class InspectedRaster:
    crs: str
    width: int
    height: int
    count: int
    band_names: list[str]
    pixel_size: dict
    bounds: dict
    nodata: dict
    driver: str
    dtype: list[str]
    transform: tuple[float, ...]


def _storage_root() -> Path:
    root = Path(get_settings().raster_storage_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_suffix(filename: str | None) -> str:
    suffix = Path(filename or "dataset.tif").suffix.lower()
    return suffix if suffix in {".tif", ".tiff", ".jp2", ".zip"} else ".bin"


def _infer_acquisition_datetime(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(?<!\d)(20\d{6})T?(\d{6})(?!\d)", value)
    if not match:
        match = re.search(r"(?<!\d)(20\d{6})(?!\d)", value)
        if not match:
            return None
        date = match.group(1)
        return f"{date[0:4]}-{date[4:6]}-{date[6:8]}T00:00:00Z"
    date, clock = match.group(1), match.group(2)
    return f"{date[0:4]}-{date[4:6]}-{date[6:8]}T{clock[0:2]}:{clock[2:4]}:{clock[4:6]}Z"


def _normalize_band_name(value: str) -> str:
    cleaned = value.strip().upper().replace(" ", "_")
    aliases = {
        "B4": "B04", "RED": "B04", "RED_BAND": "B04",
        "B3": "B03", "GREEN": "B03", "GREEN_BAND": "B03",
        "B8": "B08", "NIR": "B08", "NIR_BAND": "B08",
        "B11": "B11", "SWIR": "B11", "SWIR1": "B11", "SWIR_1": "B11",
    }
    return aliases.get(cleaned, cleaned)


def _inspect_bytes(data: bytes, *, supplied_band_names: list[str] | None = None) -> InspectedRaster:
    try:
        with MemoryFile(data) as mem:
            with mem.open() as ds:
                if ds.crs is None:
                    raise TrackBError("Raster has no CRS; georeferenced organizer data is required.")
                if ds.width <= 0 or ds.height <= 0 or ds.count <= 0:
                    raise TrackBError("Raster dimensions/bands are invalid.")
                descriptions = [str(x).strip() if x else "" for x in ds.descriptions]
                if supplied_band_names:
                    if len(supplied_band_names) != ds.count:
                        raise TrackBError("Supplied band_names count does not match raster band count.")
                    bands = [_normalize_band_name(name) for name in supplied_band_names]
                elif any(descriptions):
                    bands = [_normalize_band_name(name) if name else f"band_{i}" for i, name in enumerate(descriptions, 1)]
                else:
                    bands = [f"band_{i}" for i in range(1, ds.count + 1)]
                return InspectedRaster(
                    crs=ds.crs.to_string(),
                    width=ds.width,
                    height=ds.height,
                    count=ds.count,
                    band_names=bands,
                    pixel_size={"x": abs(float(ds.transform.a)), "y": abs(float(ds.transform.e))},
                    bounds={"left": ds.bounds.left, "bottom": ds.bounds.bottom, "right": ds.bounds.right, "top": ds.bounds.top},
                    nodata={"values": list(ds.nodatavals)},
                    driver=ds.driver,
                    dtype=list(ds.dtypes),
                    transform=tuple(ds.transform)[:6],
                )
    except TrackBError:
        raise
    except Exception as exc:
        raise TrackBError("Uploaded file is not a readable geospatial raster supported by GDAL/rasterio.") from exc


def _assert_competition_upload(source_kind: str = "upload") -> None:
    """Compatibility hook retained for callers; source eligibility is provenance-based."""
    return None

def _create_site_from_extent(
    session: Session, *, owner: User, project_id: uuid.UUID, inspected: InspectedRaster, location_type: str, name: str
):
    try:
        left, bottom, right, top = transform_bounds(inspected.crs, "EPSG:4326", inspected.bounds["left"], inspected.bounds["bottom"], inspected.bounds["right"], inspected.bounds["top"], densify_pts=21)
    except Exception as exc:
        raise TrackBError("Raster extent could not be transformed to WGS84 for challenge Site creation.") from exc
    geometry = {
        "type": "Polygon",
        "coordinates": [[[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]],
    }
    return create_site(
        session, owner=owner, project_id=project_id,
        request=SiteCreateRequest(name=f"{name} â€” {location_type.title()} Challenge Area", geometry=geometry, is_active=False),
    )


def _write_immutable(project_id: uuid.UUID, checksum: str, suffix: str, data: bytes) -> str:
    root = _storage_root()
    relative = Path(str(project_id)) / "organizer" / f"{checksum}{suffix}"
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise TrackBError("Raster storage target escaped configured root.")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            raise TrackBError("Existing raster artifact checksum mismatch.")
    else:
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_bytes(data)
        os.replace(temp, target)
    return f"local://rasters/{relative.as_posix()}"


def _local_path(uri: str | None) -> Path:
    prefix = "local://rasters/"
    if not uri or not uri.startswith(prefix):
        raise TrackBError("Track B analysis requires a locally stored organizer raster.")
    root = _storage_root()
    target = (root / uri[len(prefix):]).resolve()
    if root != target and root not in target.parents:
        raise TrackBError("Raster URI escaped configured root.")
    if not target.is_file():
        raise TrackBError("Stored raster artifact is missing.")
    return target


def _clean_band_names(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            items = [str(x).strip() for x in value if str(x).strip()]
            return [_normalize_band_name(x) for x in items] or None
    except json.JSONDecodeError:
        pass
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return [_normalize_band_name(x) for x in items] or None


async def ingest_single_raster(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None,
    file: UploadFile,
    name: str,
    location_type: str,
    temporal_role: str,
    data_stage: str,
    acquisition_datetime: str | None,
    band_names_raw: str | None,
    scene_id: str | None,
    auto_create_site: bool = False,
) -> RasterDataset:
    _assert_competition_upload()
    resolve_project_scope(session, owner=owner, project_id=project_id, state=ProjectState.ACTIVE)
    if site_id:
        resolve_site_scope(session, owner=owner, project_id=project_id, site_id=site_id, project_state=ProjectState.ACTIVE, site_state=SiteState.AVAILABLE)
    data = await file.read()
    settings = get_settings()
    if not data or len(data) > settings.raster_upload_max_bytes:
        raise TrackBError("Raster upload is empty or exceeds RASTER_UPLOAD_MAX_BYTES.")
    supplied = _clean_band_names(band_names_raw)
    inspected = _inspect_bytes(data, supplied_band_names=supplied)
    acquisition_datetime = acquisition_datetime or _infer_acquisition_datetime(file.filename)
    if site_id is None and auto_create_site:
        site_id = _create_site_from_extent(session, owner=owner, project_id=project_id, inspected=inspected, location_type=location_type, name=name).id
    checksum = hashlib.sha256(data).hexdigest()
    source_uri = _write_immutable(project_id, checksum, _safe_suffix(file.filename), data)
    dataset = RasterDataset(
        project_id=project_id,
        site_id=site_id,
        created_by_user_id=owner.id,
        name=" ".join(name.split()),
        source_kind="upload",
        provider="user_upload",
        collection="track-b-2026",
        scene_id=scene_id or checksum[:16],
        acquisition_datetime=acquisition_datetime,
        crs=inspected.crs,
        width=inspected.width,
        height=inspected.height,
        band_count=inspected.count,
        band_names=inspected.band_names,
        pixel_size=inspected.pixel_size,
        bounds=inspected.bounds,
        nodata=inspected.nodata,
        source_uri=source_uri,
        checksum_sha256=checksum,
        provenance={
            "evidence_scope": "project_controlled",
            "competition_track": "B",
            "location_type": location_type,
            "temporal_role": temporal_role,
            "data_stage": data_stage,
            "original_filename": file.filename,
            "driver": inspected.driver,
            "dtype": inspected.dtype,
            "transform": inspected.transform,
            "ingestion_method": "track_b_raster_upload_v1",
        },
        status="ready",
        is_archived=False,
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    return dataset


async def ingest_raster_bundle(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None,
    files: list[UploadFile],
    band_names_raw: str,
    name: str,
    location_type: str,
    temporal_role: str,
    data_stage: str,
    acquisition_datetime: str | None,
    scene_id: str | None,
    auto_create_site: bool = False,
) -> RasterDataset:
    _assert_competition_upload()
    bands = _clean_band_names(band_names_raw)
    if not bands or len(bands) != len(files):
        raise TrackBError("A bundle requires one explicit band name per uploaded file, in the same order.")
    if len(files) < 2:
        raise TrackBError("Raster bundle requires at least two band files.")
    resolve_project_scope(session, owner=owner, project_id=project_id, state=ProjectState.ACTIVE)
    if site_id:
        resolve_site_scope(session, owner=owner, project_id=project_id, site_id=site_id, project_state=ProjectState.ACTIVE, site_state=SiteState.AVAILABLE)

    assets: dict[str, dict] = {}
    reference: InspectedRaster | None = None
    aggregate_hash = hashlib.sha256()
    total_bytes = 0
    if not acquisition_datetime and files:
        acquisition_datetime = _infer_acquisition_datetime(files[0].filename)
    for band, upload in zip(bands, files, strict=True):
        data = await upload.read()
        total_bytes += len(data)
        if total_bytes > get_settings().raster_upload_max_bytes:
            raise TrackBError("Raster bundle exceeds RASTER_UPLOAD_MAX_BYTES.")
        inspected = _inspect_bytes(data)
        if inspected.count != 1:
            raise TrackBError("Each raw bundle asset must be a single-band raster.")
        if reference is None:
            reference = inspected
        checksum = hashlib.sha256(data).hexdigest()
        aggregate_hash.update(band.encode("utf-8")); aggregate_hash.update(checksum.encode("ascii"))
        uri = _write_immutable(project_id, checksum, _safe_suffix(upload.filename), data)
        assets[band] = {"uri": uri, "checksum_sha256": checksum, "filename": upload.filename, "crs": inspected.crs, "width": inspected.width, "height": inspected.height, "transform": inspected.transform, "pixel_size": inspected.pixel_size}

    assert reference is not None
    if site_id is None and auto_create_site:
        site_id = _create_site_from_extent(session, owner=owner, project_id=project_id, inspected=reference, location_type=location_type, name=name).id
    checksum = aggregate_hash.hexdigest()
    dataset = RasterDataset(
        project_id=project_id,
        site_id=site_id,
        created_by_user_id=owner.id,
        name=" ".join(name.split()),
        source_kind="upload",
        provider="user_upload",
        collection="track-b-2026",
        scene_id=scene_id or checksum[:16],
        acquisition_datetime=acquisition_datetime,
        crs=reference.crs,
        width=reference.width,
        height=reference.height,
        band_count=len(bands),
        band_names=bands,
        pixel_size=reference.pixel_size,
        bounds=reference.bounds,
        nodata=reference.nodata,
        source_uri=None,
        checksum_sha256=checksum,
        provenance={
            "evidence_scope": "project_controlled",
            "competition_track": "B",
            "location_type": location_type,
            "temporal_role": temporal_role,
            "data_stage": data_stage,
            "assets": assets,
            "driver": reference.driver,
            "transform": reference.transform,
            "ingestion_method": "track_b_band_bundle_v1",
        },
        status="ready",
        is_archived=False,
    )
    session.add(dataset); session.commit(); session.refresh(dataset)
    return dataset



_SENTINEL_ASSET_RE = re.compile(r"(?:^|[_\-])(B02|B03|B04|B08|B11|SCL)(?:[_\-.]|$)", re.IGNORECASE)


async def ingest_sentinel_archive(
    session: Session, *, owner: User, project_id: uuid.UUID, site_id: uuid.UUID | None, file: UploadFile,
    name: str, location_type: str, temporal_role: str, data_stage: str, acquisition_datetime: str | None,
    scene_id: str | None, auto_create_site: bool = False,
) -> RasterDataset:
    _assert_competition_upload()
    resolve_project_scope(session, owner=owner, project_id=project_id, state=ProjectState.ACTIVE)
    if site_id:
        resolve_site_scope(session, owner=owner, project_id=project_id, site_id=site_id, project_state=ProjectState.ACTIVE, site_state=SiteState.AVAILABLE)
    data = await file.read()
    if not data or len(data) > get_settings().raster_upload_max_bytes:
        raise TrackBError("Sentinel archive is empty or exceeds RASTER_UPLOAD_MAX_BYTES.")
    archive_checksum = hashlib.sha256(data).hexdigest()
    candidates: dict[str, list[tuple[float, str, bytes, InspectedRaster]]] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            expanded_total = sum(member.file_size for member in archive.infolist() if not member.is_dir())
            if expanded_total > get_settings().raster_upload_max_bytes * 2:
                raise TrackBError("Sentinel archive expands beyond the configured safety limit.")
            for member in archive.infolist():
                if member.is_dir() or member.file_size <= 0:
                    continue
                suffix = Path(member.filename).suffix.lower()
                if suffix not in {".jp2", ".tif", ".tiff"}:
                    continue
                match = _SENTINEL_ASSET_RE.search(Path(member.filename).name)
                if not match:
                    continue
                band = _normalize_band_name(match.group(1))
                payload = archive.read(member)
                inspected = _inspect_bytes(payload)
                resolution_score = abs(inspected.pixel_size["x"] * inspected.pixel_size["y"])
                candidates.setdefault(band, []).append((resolution_score, member.filename, payload, inspected))
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise TrackBError("Uploaded Sentinel archive is not a readable ZIP/SAFE package.") from exc

    if not candidates:
        raise TrackBError("No supported Sentinel bands (B02/B03/B04/B08/B11/SCL) were found in the archive.")
    if not acquisition_datetime:
        acquisition_datetime = next((_infer_acquisition_datetime(item[1]) for items in candidates.values() for item in items if _infer_acquisition_datetime(item[1])), None) or _infer_acquisition_datetime(file.filename)
    archive_uri = _write_immutable(project_id, archive_checksum, ".zip", data)
    selected = {band: sorted(items, key=lambda item: item[0])[0] for band, items in candidates.items()}
    reference_band = "B04" if "B04" in selected else "B08" if "B08" in selected else next(iter(selected))
    reference = selected[reference_band][3]
    assets: dict[str, dict] = {}
    aggregate_hash = hashlib.sha256()
    for band, (_, member_name, payload, inspected) in selected.items():
        checksum = hashlib.sha256(payload).hexdigest(); aggregate_hash.update(band.encode()); aggregate_hash.update(checksum.encode())
        uri = _write_immutable(project_id, checksum, _safe_suffix(member_name), payload)
        assets[band] = {
            "uri": uri, "checksum_sha256": checksum, "filename": member_name, "crs": inspected.crs,
            "width": inspected.width, "height": inspected.height, "transform": inspected.transform, "pixel_size": inspected.pixel_size,
        }
    if site_id is None and auto_create_site:
        site_id = _create_site_from_extent(session, owner=owner, project_id=project_id, inspected=reference, location_type=location_type, name=name).id
    checksum = aggregate_hash.hexdigest()
    dataset = RasterDataset(
        project_id=project_id, site_id=site_id, created_by_user_id=owner.id, name=" ".join(name.split()), source_kind="upload",
        provider="user_upload", collection="track-b-2026-sentinel", scene_id=scene_id or archive_checksum[:16], acquisition_datetime=acquisition_datetime,
        crs=reference.crs, width=reference.width, height=reference.height, band_count=len(selected), band_names=list(selected),
        pixel_size=reference.pixel_size, bounds=reference.bounds, nodata=reference.nodata, source_uri=None, checksum_sha256=checksum,
        provenance={
            "evidence_scope": "project_controlled", "competition_track": "B", "location_type": location_type,
            "temporal_role": temporal_role, "data_stage": data_stage, "assets": assets, "source_archive_uri": archive_uri,
            "source_archive_checksum_sha256": archive_checksum, "original_filename": file.filename, "ingestion_method": "track_b_sentinel_archive_v1",
            "selected_highest_resolution_per_band": True,
        }, status="ready", is_archived=False,
    )
    session.add(dataset); session.commit(); session.refresh(dataset); return dataset

def list_track_b_datasets(session: Session, *, owner: User, project_id: uuid.UUID) -> list[RasterDataset]:
    resolve_project_scope(session, owner=owner, project_id=project_id, state=ProjectState.ACTIVE)
    return list(session.scalars(select(RasterDataset).where(RasterDataset.project_id == project_id, RasterDataset.is_archived.is_(False)).order_by(RasterDataset.created_at.desc())))


def archive_track_b_dataset(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    raster_id: uuid.UUID,
) -> RasterDataset:
    resolve_project_scope(
        session,
        owner=owner,
        project_id=project_id,
        state=ProjectState.ACTIVE,
    )

    dataset = session.scalar(
        select(RasterDataset).where(
            RasterDataset.id == raster_id,
            RasterDataset.project_id == project_id,
        )
    )

    if dataset is None:
        raise TrackBError("Track B raster dataset not found.")

    if dataset.is_archived:
        raise TrackBError("Track B raster dataset is already archived.")

    dataset.is_archived = True
    dataset.status = "archived"

    session.commit()
    session.refresh(dataset)
    return dataset


def _band_asset(dataset: RasterDataset, band: str) -> tuple[Path, int]:
    assets = (dataset.provenance or {}).get("assets") or {}
    if band in assets:
        return _local_path(assets[band].get("uri")), 1
    if band not in dataset.band_names:
        raise TrackBError(f"Dataset {dataset.name!r} does not contain required band {band}.")
    return _local_path(dataset.source_uri), dataset.band_names.index(band) + 1


def _read_band(dataset: RasterDataset, band: str, *, categorical: bool = False) -> tuple[np.ndarray, dict]:
    path, index = _band_asset(dataset, band)
    with rasterio.open(path) as ds:
        max_pixels = get_settings().track_b_max_analysis_pixels
        original_pixels = ds.width * ds.height
        if original_pixels > max_pixels:
            scale = math.sqrt(max_pixels / original_pixels)
            out_width = max(1, int(ds.width * scale)); out_height = max(1, int(ds.height * scale))
        else:
            out_width, out_height = ds.width, ds.height
        resampling = Resampling.nearest if categorical else Resampling.bilinear
        raw = ds.read(index, out_shape=(out_height, out_width), masked=True, resampling=resampling)
        arr = raw.astype("float32").filled(np.nan)
        transform = ds.transform * ds.transform.scale(ds.width / out_width, ds.height / out_height)
        return arr, {
            "crs": ds.crs, "transform": transform, "width": out_width, "height": out_height, "bounds": ds.bounds, "nodata": ds.nodata,
            "downsampled": (out_width != ds.width or out_height != ds.height), "original_width": ds.width, "original_height": ds.height,
        }


def _first_band(dataset: RasterDataset, *, categorical: bool = False) -> tuple[np.ndarray, dict]:
    if (dataset.provenance or {}).get("assets"):
        return _read_band(dataset, dataset.band_names[0], categorical=categorical)
    path = _local_path(dataset.source_uri)
    with rasterio.open(path) as ds:
        max_pixels = get_settings().track_b_max_analysis_pixels; original_pixels = ds.width * ds.height
        if original_pixels > max_pixels:
            scale = math.sqrt(max_pixels / original_pixels); out_width = max(1, int(ds.width * scale)); out_height = max(1, int(ds.height * scale))
        else: out_width, out_height = ds.width, ds.height
        raw = ds.read(1, out_shape=(out_height, out_width), masked=True, resampling=Resampling.nearest if categorical else Resampling.bilinear)
        transform = ds.transform * ds.transform.scale(ds.width / out_width, ds.height / out_height)
        return raw.astype("float32").filled(np.nan), {
            "crs": ds.crs, "transform": transform, "width": out_width, "height": out_height, "bounds": ds.bounds, "nodata": ds.nodata,
            "downsampled": (out_width != ds.width or out_height != ds.height), "original_width": ds.width, "original_height": ds.height,
        }


def _aligned(after: np.ndarray, after_meta: dict, before_meta: dict, *, categorical: bool = False) -> np.ndarray:
    if (after_meta["crs"] == before_meta["crs"] and after_meta["transform"] == before_meta["transform"] and after.shape == (before_meta["height"], before_meta["width"])):
        return after
    out = np.full((before_meta["height"], before_meta["width"]), np.nan, dtype="float32")
    reproject(
        source=after,
        destination=out,
        src_transform=after_meta["transform"],
        src_crs=after_meta["crs"],
        dst_transform=before_meta["transform"],
        dst_crs=before_meta["crs"],
        resampling=Resampling.nearest if categorical else Resampling.bilinear,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    return out


def _quality_mask(dataset: RasterDataset, reference_meta: dict) -> np.ndarray:
    mask = np.ones((reference_meta["height"], reference_meta["width"]), dtype=bool)
    if "SCL" not in dataset.band_names:
        return mask
    scl_raw, scl_meta = _read_band(dataset, "SCL", categorical=True)
    scl = _aligned(scl_raw, scl_meta, reference_meta, categorical=True)
    # Sentinel-2 L2A SCL invalid/uncertain: no-data, saturated, cloud shadow,
    # medium/high cloud, cirrus and snow/ice.
    invalid_classes = np.array([0, 1, 3, 8, 9, 10, 11], dtype="float32")
    return np.isfinite(scl) & ~np.isin(np.rint(scl), invalid_classes)


def _index(dataset: RasterDataset, kind: str) -> tuple[np.ndarray, dict]:
    required = {"ndvi": ("B08", "B04"), "ndwi": ("B03", "B08"), "ndbi": ("B11", "B08")}[kind]
    a, meta = _read_band(dataset, required[0]); b_raw, b_meta = _read_band(dataset, required[1])
    b = _aligned(b_raw, b_meta, meta)
    denom = a + b
    out = np.full_like(a, np.nan, dtype="float32")
    valid = np.isfinite(a) & np.isfinite(b) & (denom != 0)
    out[valid] = (a[valid] - b[valid]) / denom[valid]
    return out, meta


def _stretch_uint8(array: np.ndarray) -> np.ndarray:
    valid = array[np.isfinite(array)]
    if valid.size == 0:
        return np.zeros(array.shape, dtype="uint8")
    low, high = np.nanpercentile(valid, [2, 98])
    if not math.isfinite(float(low)) or not math.isfinite(float(high)) or high <= low:
        low, high = float(np.nanmin(valid)), float(np.nanmax(valid))
    if high <= low:
        return np.zeros(array.shape, dtype="uint8")
    scaled = np.clip((array - low) / (high - low), 0, 1) * 255
    return np.nan_to_num(scaled, nan=0).astype("uint8")


def render_dataset_quicklook(dataset: RasterDataset, max_size: int = 1200) -> bytes:
    if {"B04", "B03", "B02"} <= set(dataset.band_names):
        red, meta = _read_band(dataset, "B04")
        green_raw, green_meta = _read_band(dataset, "B03")
        blue_raw, blue_meta = _read_band(dataset, "B02")
        green = _aligned(green_raw, green_meta, meta); blue = _aligned(blue_raw, blue_meta, meta)
        rgb = np.dstack([_stretch_uint8(red), _stretch_uint8(green), _stretch_uint8(blue)])
        image = Image.fromarray(rgb, mode="RGB")
    else:
        band, _ = _first_band(dataset); image = Image.fromarray(_stretch_uint8(band), mode="L").convert("RGB")
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    output = io.BytesIO(); image.save(output, format="PNG", optimize=True); return output.getvalue()


def _pixel_area_sqm(meta: dict) -> tuple[float | None, str | None]:
    crs = CRS.from_user_input(meta["crs"])
    transform = meta["transform"]
    if crs.is_projected:
        factor = crs.axis_info[0].unit_conversion_factor if crs.axis_info else 1.0
        return abs(transform.a * transform.e) * factor * factor, None
    if crs.is_geographic:
        bounds = meta["bounds"]
        geod = Geod(ellps="WGS84")
        lons = [bounds.left, bounds.right, bounds.right, bounds.left]
        lats = [bounds.bottom, bounds.bottom, bounds.top, bounds.top]
        area, _ = geod.polygon_area_perimeter(lons, lats)
        total = max(1, meta["width"] * meta["height"])
        return abs(area) / total, "Changed area uses average geodesic pixel area because the raster CRS is geographic."
    return None, "Changed area could not be calculated because CRS units are not resolvable."


def _write_change_artifacts(project_id: uuid.UUID, analysis_id: uuid.UUID, mask: np.ndarray, meta: dict) -> tuple[str, str, list[str]]:
    root = _storage_root(); relative = Path("analysis") / str(project_id) / str(analysis_id); folder = (root / relative).resolve(); folder.mkdir(parents=True, exist_ok=True)
    mask_path = folder / "change_mask.tif"
    profile = {"driver": "GTiff", "height": mask.shape[0], "width": mask.shape[1], "count": 1, "dtype": "uint8", "crs": meta["crs"], "transform": meta["transform"], "nodata": 0, "compress": "deflate"}
    with rasterio.open(mask_path, "w", **profile) as dst: dst.write(mask.astype("uint8"), 1)

    geoms = []
    for geom, value in shapes(mask.astype("uint8"), mask=mask.astype(bool), transform=meta["transform"]):
        if value == 1:
            try: geoms.append(shape(geom))
            except Exception: pass
    limitations: list[str] = []
    features = []
    if geoms:
        parts = geoms
        if len(parts) > 500:
            parts = sorted(parts, key=lambda g: g.area, reverse=True)[:500]
            limitations.append("Change-region GeoJSON was capped at the 500 largest connected regions for interactive display; the GeoTIFF mask retains the full result.")
        for g in parts:
            geom = mapping(g)
            try:
                geom = transform_geom(meta["crs"], "EPSG:4326", geom, precision=7)
            except Exception as exc:
                raise TrackBError("Change geometry could not be transformed to EPSG:4326 for map display.") from exc
            features.append({"type": "Feature", "properties": {"change": True}, "geometry": geom})
    geojson = {"type": "FeatureCollection", "features": features}
    geo_path = folder / "change_regions.geojson"; geo_path.write_text(json.dumps(geojson), encoding="utf-8")
    return f"change_mask.tif", f"change_regions.geojson", limitations


def _assert_pair(before: RasterDataset, after: RasterDataset, request: TrackBAnalysisRequest) -> None:
    for ds in (before, after):
        if ds.site_id and ds.site_id != request.site_id:
            raise TrackBError("Selected raster is linked to a different site.")
    bp = before.provenance or {}; ap = after.provenance or {}
    if bp.get("temporal_role") == "after" or ap.get("temporal_role") == "before":
        raise TrackBError("Temporal role provenance conflicts with the selected before/after order.")
    if bp.get("location_type") and ap.get("location_type") and bp.get("location_type") != ap.get("location_type"):
        raise TrackBError("Urban and rural rasters cannot be mixed in one temporal pair.")
    if bp.get("data_stage") and ap.get("data_stage") and bp.get("data_stage") != ap.get("data_stage"):
        raise TrackBError("Temporal comparison must pair equivalent raw/raw or processed/processed datasets.")
    if before.acquisition_datetime and after.acquisition_datetime and before.acquisition_datetime >= after.acquisition_datetime:
        raise TrackBError("Before acquisition datetime must be earlier than after acquisition datetime.")


def analyze_temporal_pair(session: Session, *, owner: User, project_id: uuid.UUID, request: TrackBAnalysisRequest) -> dict:
    site_scope = resolve_site_scope(session, owner=owner, project_id=project_id, site_id=request.site_id, project_state=ProjectState.ACTIVE, site_state=SiteState.AVAILABLE)
    before = get_raster(session, owner=owner, project_id=project_id, raster_id=request.before_raster_id)
    after = get_raster(session, owner=owner, project_id=project_id, raster_id=request.after_raster_id)
    _assert_pair(before, after, request)

    mode = request.mode
    if mode == "auto":
        common = set(before.band_names) & set(after.band_names)
        mode = "ndvi" if {"B04", "B08"} <= common else "classified" if (before.provenance or {}).get("data_stage") == (after.provenance or {}).get("data_stage") == "processed" and before.band_count == after.band_count == 1 else "spectral"

    if mode in {"ndvi", "ndwi", "ndbi"}:
        b, meta = _index(before, mode); a_raw, a_meta = _index(after, mode); a = _aligned(a_raw, a_meta, meta)
        delta = np.abs(a - b); valid = np.isfinite(b) & np.isfinite(a); changed = valid & (delta >= request.absolute_delta_threshold)
        method = f"{mode}-absolute-delta-v1"; mean_before = float(np.nanmean(b[valid])) if valid.any() else None; mean_after = float(np.nanmean(a[valid])) if valid.any() else None
        index_limitation = f"{mode.upper()} change is an index measurement and does not by itself prove planning causation or statutory land-use change."
    elif mode == "classified":
        b, meta = _first_band(before, categorical=True); a_raw, a_meta = _first_band(after, categorical=True); a = _aligned(a_raw, a_meta, meta, categorical=True)
        valid = np.isfinite(b) & np.isfinite(a); changed = valid & (a != b); method = "categorical-class-change-v1"; mean_before = mean_after = None
        index_limitation = "Class change assumes the organizer processed rasters use the same class coding between dates."
    else:
        common = [band for band in before.band_names if band in after.band_names and band != "SCL"]
        if not common:
            # fall back to band 1 for processed/unknown rasters
            b, meta = _first_band(before); a_raw, a_meta = _first_band(after); a = _aligned(a_raw, a_meta, meta)
            scale = np.nanpercentile(np.abs(np.concatenate([b[np.isfinite(b)], a[np.isfinite(a)]])), 95) if (np.isfinite(b).any() and np.isfinite(a).any()) else 1.0
            scale = float(scale) if scale and math.isfinite(float(scale)) else 1.0
            delta = np.abs(a - b) / scale; valid = np.isfinite(b) & np.isfinite(a); changed = valid & (delta >= request.absolute_delta_threshold); method = "normalized-single-band-change-v1"; mean_before = float(np.nanmean(b[valid])) if valid.any() else None; mean_after = float(np.nanmean(a[valid])) if valid.any() else None
        else:
            accum = None; valid = None; meta = None
            for band in common:
                b, bm = _read_band(before, band); ar, am = _read_band(after, band); a = _aligned(ar, am, bm)
                this_valid = np.isfinite(b) & np.isfinite(a)
                scale = np.nanpercentile(np.abs(np.concatenate([b[this_valid], a[this_valid]])), 95) if this_valid.any() else 1.0
                scale = float(scale) if scale and math.isfinite(float(scale)) else 1.0
                d = ((a - b) / scale) ** 2
                accum = d if accum is None else accum + d; valid = this_valid if valid is None else valid & this_valid; meta = bm
            assert accum is not None and valid is not None and meta is not None
            distance = np.sqrt(accum / max(1, len(common))); changed = valid & (distance >= request.absolute_delta_threshold); method = "normalized-multiband-spectral-distance-v1"; mean_before = mean_after = None
        index_limitation = "Spectral change identifies radiometric difference; professional interpretation is required to classify the cause."

    valid = valid & _quality_mask(before, meta) & _quality_mask(after, meta)
    changed = changed & valid

    site_geometry = ewkt_to_geojson(site_scope.site.geometry)
    try:
        geometry_in_raster_crs = transform_geom("EPSG:4326", meta["crs"], site_geometry, precision=3)
        target_mask = geometry_mask([geometry_in_raster_crs], out_shape=(meta["height"], meta["width"]), transform=meta["transform"], invert=True)
    except Exception as exc:
        raise TrackBError("Active Site geometry could not be projected onto the raster grid.") from exc
    target_pixels = int(target_mask.sum())
    if target_pixels == 0:
        raise TrackBError("Selected raster does not cover the selected Site geometry.")
    valid = valid & target_mask
    changed = changed & valid
    valid_count = int(valid.sum()); coverage = valid_count / target_pixels * 100.0 if target_pixels else 0.0
    if coverage < request.minimum_usable_coverage_percent:
        raise TrackBError(f"Usable temporal coverage {coverage:.2f}% is below required {request.minimum_usable_coverage_percent:.2f}%.")
    changed_count = int(changed.sum()); changed_pct = changed_count / valid_count * 100.0 if valid_count else 0.0
    pixel_area, area_lim = _pixel_area_sqm(meta); changed_ha = changed_count * pixel_area / 10000.0 if pixel_area is not None else None
    analysis_id = uuid.uuid4(); mask_name, geo_name, artifact_limits = _write_change_artifacts(project_id, analysis_id, changed, meta)
    limitations = [index_limitation, "Cloud/shadow masking uses Sentinel SCL when supplied; otherwise it is limited to available raster validity/nodata information.", "Results are decision-support evidence and require professional review before material planning conclusions.", *artifact_limits]
    if meta.get("downsampled"):
        limitations.append(f"Large raster was processed on a controlled analysis grid ({meta['width']}Ã—{meta['height']}) from {meta['original_width']}Ã—{meta['original_height']} to respect the configured memory safety ceiling.")
    if area_lim: limitations.append(area_lim)
    metric_name = mode.upper() if mode in {"ndvi", "ndwi", "ndbi"} else "Temporal"
    summary = f"{metric_name} analysis measured {changed_pct:.2f}% changed pixels across {coverage:.2f}% usable coverage"
    if changed_ha is not None: summary += f", equivalent to approximately {changed_ha:.2f} ha within the raster analysis footprint"
    summary += "."
    payload = {
        "analysis_id": analysis_id, "project_id": project_id, "site_id": request.site_id, "location_type": (before.provenance or {}).get("location_type"), "data_stage": (before.provenance or {}).get("data_stage"), "mode": mode, "method": method,
        "before_raster_id": before.id, "after_raster_id": after.id, "before_datetime": before.acquisition_datetime, "after_datetime": after.acquisition_datetime,
        "usable_coverage_percent": coverage, "changed_pixel_count": changed_count, "valid_pixel_count": valid_count, "changed_percentage": changed_pct,
        "changed_area_hectares": changed_ha, "mean_before": mean_before, "mean_after": mean_after,
        "metrics": [
            {"key": "changed_percentage", "label": "Changed pixels", "value": round(changed_pct, 3), "unit": "%"},
            {"key": "usable_coverage", "label": "Usable coverage", "value": round(coverage, 3), "unit": "%"},
            *([{"key": "changed_area", "label": "Changed area", "value": round(changed_ha, 3), "unit": "ha"}] if changed_ha is not None else []),
            *([{"key": "mean_before", "label": f"Mean {mode.upper()} before", "value": round(mean_before, 4), "unit": None}, {"key": "mean_after", "label": f"Mean {mode.upper()} after", "value": round(mean_after, 4), "unit": None}] if mean_before is not None and mean_after is not None else []),
        ],
        "change_geojson_url": f"/api/v1/projects/{project_id}/track-b/artifacts/{analysis_id}/{geo_name}",
        "change_mask_url": f"/api/v1/projects/{project_id}/track-b/artifacts/{analysis_id}/{mask_name}",
        "evidence": [
            {"kind": "raster_dataset", "id": str(before.id), "checksum_sha256": before.checksum_sha256, "role": "before", "scope": (before.provenance or {}).get("evidence_scope") or "project_controlled"},
            {"kind": "raster_dataset", "id": str(after.id), "checksum_sha256": after.checksum_sha256, "role": "after", "scope": (after.provenance or {}).get("evidence_scope") or "project_controlled"},
            {"kind": "site_geometry", "id": str(site_scope.site.id), "geometry_hash": site_scope.site.geometry_hash, "geometry_revision": site_scope.site.geometry_revision, "scope": "server_owned"},
        ],
        "limitations": limitations, "summary": summary,
        "report_url": f"/api/v1/projects/{project_id}/track-b/analyses/{analysis_id}/report",
    }
    _persist_analysis_manifest(project_id, analysis_id, payload)
    return payload


def _analysis_folder(project_id: uuid.UUID, analysis_id: uuid.UUID) -> Path:
    root = _storage_root()
    folder = (root / "analysis" / str(project_id) / str(analysis_id)).resolve()
    if root != folder and root not in folder.parents:
        raise TrackBError("Analysis path escaped configured root.")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _persist_analysis_manifest(project_id: uuid.UUID, analysis_id: uuid.UUID, payload: dict) -> None:
    folder = _analysis_folder(project_id, analysis_id)
    (folder / "analysis.json").write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")


def compose_track_b_report(project_id: uuid.UUID, analysis_id: uuid.UUID) -> Path:
    folder = _analysis_folder(project_id, analysis_id)
    manifest = folder / "analysis.json"
    if not manifest.is_file():
        raise TrackBError("Track B analysis manifest not found.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    output = folder / "track_b_evidence_report.pdf"
    c = canvas.Canvas(str(output), pagesize=A4)
    width, height = A4
    margin = 46; y = height - 48
    c.setTitle("GeoPilot Track B Evidence Report")
    c.setFont("Helvetica-Bold", 18); c.drawString(margin, y, "GeoPilot AI â€” Track B Evidence Report"); y -= 24
    c.setFont("Helvetica", 8); c.drawString(margin, y, f"Analysis ID: {analysis_id}"); y -= 22
    c.setFont("Helvetica-Bold", 11); c.drawString(margin, y, "Measured temporal result"); y -= 16
    c.setFont("Helvetica", 9)
    lines = [
        f"Mode / method: {data.get('mode')} / {data.get('method')}",
        f"Usable coverage: {float(data.get('usable_coverage_percent', 0)):.2f}%",
        f"Changed pixels: {float(data.get('changed_percentage', 0)):.2f}% ({data.get('changed_pixel_count')} pixels)",
        f"Changed area: {data.get('changed_area_hectares')} ha",
        f"Before: {data.get('before_datetime') or 'date not supplied'}",
        f"After: {data.get('after_datetime') or 'date not supplied'}",
    ]
    for line in lines: c.drawString(margin, y, line); y -= 13
    y -= 8; c.setFont("Helvetica-Bold", 11); c.drawString(margin, y, "Grounded summary"); y -= 15; c.setFont("Helvetica", 9)
    for line in _wrap_report_text(str(data.get("summary") or ""), 95): c.drawString(margin, y, line); y -= 12
    y -= 8; c.setFont("Helvetica-Bold", 11); c.drawString(margin, y, "Evidence lineage"); y -= 15; c.setFont("Helvetica", 8)
    for ev in data.get("evidence", []):
        line = f"{ev.get('kind')} | {ev.get('role', '')} | {ev.get('id')} | {ev.get('checksum_sha256', ev.get('geometry_hash', ''))}"
        for wrapped in _wrap_report_text(line, 105): c.drawString(margin, y, wrapped); y -= 10
    y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(margin, y, "Limitations / professional review boundary"); y -= 15; c.setFont("Helvetica", 8)
    for limitation in data.get("limitations", []):
        for wrapped in _wrap_report_text("â€¢ " + limitation, 108):
            if y < 55: c.showPage(); y = height - 48; c.setFont("Helvetica", 8)
            c.drawString(margin, y, wrapped); y -= 10
    decision_path = folder / "planner_decision.json"
    if decision_path.is_file():
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        if y < 180:
            c.showPage(); y = height - 48
        c.setFont("Helvetica-Bold", 11); c.drawString(margin, y, "GeoPilot AI planner decision workspace"); y -= 15
        c.setFont("Helvetica", 8)
        decision_lines = [
            f"Triage priority (non-statutory): {decision.get('priority')}",
            f"AI confidence: {decision.get('confidence')}",
            f"Issue: {decision.get('issue')}",
            f"Planning implication: {decision.get('planning_implication')}",
            f"Evidence summary: {decision.get('evidence_summary')}",
        ]
        for line in decision_lines:
            for wrapped in _wrap_report_text(str(line), 108):
                if y < 55: c.showPage(); y = height - 48; c.setFont("Helvetica", 8)
                c.drawString(margin, y, wrapped); y -= 10
        for action in decision.get("recommended_actions", []):
            for wrapped in _wrap_report_text("Action: " + str(action.get("action", "")), 108):
                if y < 55: c.showPage(); y = height - 48; c.setFont("Helvetica", 8)
                c.drawString(margin, y, wrapped); y -= 10
        y -= 6
    y -= 12; c.setFont("Helvetica-Bold", 8); c.drawString(margin, y, "Evidence provenance declaration")
    y -= 11; c.setFont("Helvetica", 8)
    declaration = "This analysis uses evidence with recorded provenance and deterministic processing lineage. GeoPilot may combine project evidence, server-derived measurements, and approved official acquired sources. GeoPilot is decision support and does not issue statutory approval or certification."
    for wrapped in _wrap_report_text(declaration, 108): c.drawString(margin, y, wrapped); y -= 10
    c.save(); return output


def _wrap_report_text(text: str, width: int) -> list[str]:
    words = text.split(); lines: list[str] = []; line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if len(candidate) > width and line:
            lines.append(line); line = word
        else: line = candidate
    if line: lines.append(line)
    return lines or [""]



def artifact_path(project_id: uuid.UUID, analysis_id: uuid.UUID, filename: str) -> Path:
    if filename not in {"change_regions.geojson", "change_mask.tif", "track_b_evidence_report.pdf", "analysis.json"}:
        raise TrackBError("Unknown Track B artifact.")
    root = _storage_root(); target = (root / "analysis" / str(project_id) / str(analysis_id) / filename).resolve()
    if root != target and root not in target.parents: raise TrackBError("Artifact path escaped configured root.")
    if not target.is_file(): raise TrackBError("Track B artifact not found.")
    return target


