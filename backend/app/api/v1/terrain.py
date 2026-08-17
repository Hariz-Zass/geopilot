from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.raster import RasterDatasetResponse
from app.services.terrain_ingestion import ingest_site_dem
from app.services.terrain_analysis import TerrainAnalysisError, TerrainEvidenceMissing, calculate_site_terrain_summary


router = APIRouter(
    prefix="/projects/{project_id}/sites/{site_id}/terrain",
    tags=["Terrain"],
)


def _error(exc: Exception) -> AppError:
    return AppError(
        code="terrain_invalid",
        message=str(exc),
        status_code=422,
    )


@router.post(
    "/dem",
    response_model=RasterDatasetResponse,
    status_code=201,
)
async def upload_dem(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    file: UploadFile = File(...),
    name: str = Form(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        return await ingest_site_dem(
            session,
            owner=current_user,
            project_id=project_id,
            site_id=site_id,
            file=file,
            name=name,
        )
    except Exception as exc:
        session.rollback()
        raise _error(exc) from exc


@router.post("/analysis")
def analyze_terrain(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        summary = calculate_site_terrain_summary(
            session,
            owner=current_user,
            project_id=project_id,
            site_id=site_id,
        )
        return {
            "raster_id": str(summary.raster_id),
            "raster_checksum_sha256": summary.raster_checksum_sha256,
            "source_uri": summary.source_uri,
            "crs": summary.crs,
            "valid_pixel_count": summary.valid_pixel_count,
            "elevation_min_m": summary.elevation_min_m,
            "elevation_max_m": summary.elevation_max_m,
            "elevation_mean_m": summary.elevation_mean_m,
            "slope_min_degrees": summary.slope_min_degrees,
            "slope_max_degrees": summary.slope_max_degrees,
            "slope_mean_degrees": summary.slope_mean_degrees,
            "max_slope_longitude": summary.max_slope_longitude,
            "max_slope_latitude": summary.max_slope_latitude,
        }
    except (TerrainEvidenceMissing, TerrainAnalysisError) as exc:
        session.rollback()
        raise _error(exc) from exc
    except Exception as exc:
        session.rollback()
        raise _error(exc) from exc
