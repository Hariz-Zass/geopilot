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


CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"
CDSE_DEM_COLLECTION = "COPERNICUS_30"
CDSE_DEM_RESOLUTION_DEGREES = 0.0003
CDSE_HTTP_TIMEOUT_SECONDS = 60.0
CDSE_MAX_DEM_BYTES = 256 * 1024 * 1024

_CDSE_DEM_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: ["DEM"],
    output: {
      id: "default",
      bands: 1,
      sampleType: SampleType.FLOAT32
    }
  }
}
function evaluatePixel(sample) {
  return [sample.DEM]
}
"""


def _geometry_bbox(site_geometry: dict) -> list[float]:
    try:
        geom_type = site_geometry.get("type")
        coordinates = site_geometry.get("coordinates")
        if geom_type not in {"Polygon", "MultiPolygon"} or not coordinates:
            raise ValueError("unsupported geometry")

        points: list[tuple[float, float]] = []

        def walk(value: object) -> None:
            if (
                isinstance(value, (list, tuple))
                and len(value) >= 2
                and isinstance(value[0], (int, float))
                and isinstance(value[1], (int, float))
            ):
                points.append((float(value[0]), float(value[1])))
                return
            if isinstance(value, (list, tuple)):
                for item in value:
                    walk(item)

        walk(coordinates)
        if not points:
            raise ValueError("empty geometry")

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
        if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            raise ValueError("degenerate bounds")
        if bbox[0] < -180 or bbox[2] > 180 or bbox[1] < -90 or bbox[3] > 90:
            raise ValueError("bounds are not CRS84 longitude/latitude")
        return bbox
    except (AttributeError, TypeError, ValueError) as exc:
        raise TerrainAcquisitionError(
            "Site geometry must be a valid Polygon/MultiPolygon in CRS84/WGS84 for CDSE DEM acquisition."
        ) from exc


class CopernicusDemProvider:
    """Official CDSE Sentinel Hub Process API adapter for Copernicus DEM GLO-30."""

    name = "copernicus_cdse"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        token_url: str = CDSE_TOKEN_URL,
        process_url: str = CDSE_PROCESS_URL,
    ):
        self._client = client
        self._token_url = token_url
        self._process_url = process_url

    def _request_token(self, client: httpx.Client, *, client_id: str, client_secret: str) -> str:
        try:
            response = client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise TerrainAcquisitionError("CDSE OAuth token endpoint could not be reached.") from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise TerrainAcquisitionError(
                f"CDSE OAuth authentication failed with HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise TerrainAcquisitionError("CDSE OAuth returned an invalid token response.") from exc

        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise TerrainAcquisitionError("CDSE OAuth response did not contain an access token.")
        return token

    def _process_payload(self, bbox: list[float]) -> dict:
        return {
            "input": {
                "bounds": {
                    "properties": {
                        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
                    },
                    "bbox": bbox,
                },
                "data": [
                    {
                        "type": "dem",
                        "dataFilter": {"demInstance": CDSE_DEM_COLLECTION},
                        "processing": {
                            "upsampling": "BILINEAR",
                            "downsampling": "BILINEAR",
                        },
                    }
                ],
            },
            "output": {
                "resx": CDSE_DEM_RESOLUTION_DEGREES,
                "resy": CDSE_DEM_RESOLUTION_DEGREES,
                "responses": [
                    {
                        "identifier": "default",
                        "format": {"type": "image/tiff"},
                    }
                ],
            },
            "evalscript": _CDSE_DEM_EVALSCRIPT,
        }

    def acquire(
        self,
        *,
        site_geometry: dict,
        target_crs: str,
    ) -> AcquiredTerrainArtifact:
        settings = get_settings()
        client_id = settings.terrain_cdse_client_id
        client_secret = settings.terrain_cdse_client_secret
        if not client_id or not client_secret:
            raise TerrainAcquisitionError(
                "Automatic Copernicus DEM acquisition is not configured. "
                "CDSE OAuth client credentials are required."
            )

        bbox = _geometry_bbox(site_geometry)
        owns_client = self._client is None
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(CDSE_HTTP_TIMEOUT_SECONDS),
            follow_redirects=False,
        )

        try:
            token = self._request_token(
                client,
                client_id=client_id,
                client_secret=client_secret,
            )
            try:
                response = client.post(
                    self._process_url,
                    json=self._process_payload(bbox),
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "image/tiff",
                    },
                )
            except httpx.HTTPError as exc:
                raise TerrainAcquisitionError("CDSE DEM Process API could not be reached.") from exc

            if response.status_code < 200 or response.status_code >= 300:
                raise TerrainAcquisitionError(
                    f"CDSE DEM Process API failed with HTTP {response.status_code}."
                )

            content_type = response.headers.get("content-type", "").lower()
            data = response.content
            if len(data) == 0:
                raise TerrainAcquisitionError("CDSE DEM Process API returned an empty response.")
            if len(data) > CDSE_MAX_DEM_BYTES:
                raise TerrainAcquisitionError("CDSE DEM response exceeded the configured safety limit.")
            if "json" in content_type or "html" in content_type:
                raise TerrainAcquisitionError("CDSE DEM Process API returned a non-raster payload.")

            try:
                with MemoryFile(data) as mem:
                    with mem.open() as ds:
                        if ds.driver != "GTiff" or ds.count < 1 or ds.crs is None:
                            raise TerrainAcquisitionError("CDSE DEM response is not a valid georeferenced GeoTIFF.")
                        original_crs = ds.crs.to_string()
                        width = ds.width
                        height = ds.height
                        dtype = ds.dtypes[0]
            except TerrainAcquisitionError:
                raise
            except Exception as exc:
                raise TerrainAcquisitionError("CDSE DEM response could not be opened as GeoTIFF.") from exc

            bbox_ref = ",".join(f"{x:.6f}" for x in bbox)
            return AcquiredTerrainArtifact(
                data=data,
                provider=self.name,
                collection="copernicus-dem-glo-30",
                scene_id=f"cdse-dem-glo30-{hashlib.sha256(bbox_ref.encode('utf-8')).hexdigest()[:16]}",
                acquisition_datetime=None,
                source_reference=self._process_url,
                original_crs=original_crs,
                metadata={
                    "dataset": "Copernicus DEM GLO-30",
                    "dem_instance": CDSE_DEM_COLLECTION,
                    "requested_bbox_crs": "CRS84",
                    "requested_bbox": bbox,
                    "requested_resolution_degrees": CDSE_DEM_RESOLUTION_DEGREES,
                    "returned_width": width,
                    "returned_height": height,
                    "returned_dtype": dtype,
                    "normalization_target_crs": target_crs,
                },
            )
        finally:
            if owns_client:
                client.close()


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

