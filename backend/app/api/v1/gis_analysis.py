from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.gis_analysis import (
    FeatureDistanceResult,
    FeatureOverlapResult,
    NearestFeaturesResult,
    SiteAreaResult,
    SiteBufferRequest,
    SiteBufferResult,
)
from app.services.gis_analysis import (
    GISAnalysisResultError,
    GISAnalysisStateError,
    calculate_feature_distance,
    calculate_feature_overlap,
    calculate_site_area,
    calculate_site_buffer,
    find_nearest_features,
)
from app.services.gis_features import GISFeatureNotFoundError
from app.services.gis_layers import GISLayerNotFoundError, GISLayerProjectNotFoundError
from app.services.isolation import (
    ProjectScopeNotFoundError,
    ScopeStateError,
    SiteScopeNotFoundError,
)

router = APIRouter(
    prefix="/projects/{project_id}/sites/{site_id}/analysis/gis",
    tags=["gis-analysis"],
)


def _translate(exc: Exception) -> AppError:
    if isinstance(
        exc,
        (
            ProjectScopeNotFoundError,
            SiteScopeNotFoundError,
            GISLayerProjectNotFoundError,
            GISLayerNotFoundError,
            GISFeatureNotFoundError,
        ),
    ):
        return AppError(status_code=404, code="gis_analysis_scope_not_found", message="Analysis scope or evidence was not found")
    if isinstance(exc, (ScopeStateError, GISAnalysisStateError)):
        return AppError(status_code=409, code="gis_analysis_scope_invalid", message=str(exc) or "Analysis scope is not eligible")
    if isinstance(exc, GISAnalysisResultError):
        return AppError(status_code=503, code="gis_analysis_result_invalid", message="Deterministic GIS analysis did not produce a valid result")
    raise exc


@router.get("/area", response_model=SiteAreaResult)
def area(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    owner: User = Depends(get_current_user),
) -> SiteAreaResult:
    try:
        return calculate_site_area(session, owner=owner, project_id=project_id, site_id=site_id)
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/layers/{layer_id}/nearest", response_model=NearestFeaturesResult)
def nearest(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    layer_id: uuid.UUID,
    limit: int = Query(default=5, ge=1, le=100),
    max_distance_m: float | None = Query(default=None, gt=0, le=10_000_000),
    session: Session = Depends(get_db_session),
    owner: User = Depends(get_current_user),
) -> NearestFeaturesResult:
    try:
        return find_nearest_features(
            session,
            owner=owner,
            project_id=project_id,
            site_id=site_id,
            layer_id=layer_id,
            limit=limit,
            max_distance_m=max_distance_m,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/layers/{layer_id}/features/{feature_id}/distance", response_model=FeatureDistanceResult)
def feature_distance(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    layer_id: uuid.UUID,
    feature_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    owner: User = Depends(get_current_user),
) -> FeatureDistanceResult:
    try:
        return calculate_feature_distance(
            session,
            owner=owner,
            project_id=project_id,
            site_id=site_id,
            layer_id=layer_id,
            feature_id=feature_id,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/layers/{layer_id}/features/{feature_id}/overlap", response_model=FeatureOverlapResult)
def feature_overlap(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    layer_id: uuid.UUID,
    feature_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    owner: User = Depends(get_current_user),
) -> FeatureOverlapResult:
    try:
        return calculate_feature_overlap(
            session,
            owner=owner,
            project_id=project_id,
            site_id=site_id,
            layer_id=layer_id,
            feature_id=feature_id,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/buffer", response_model=SiteBufferResult, status_code=status.HTTP_200_OK)
def buffer(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    request: SiteBufferRequest,
    session: Session = Depends(get_db_session),
    owner: User = Depends(get_current_user),
) -> SiteBufferResult:
    try:
        return calculate_site_buffer(
            session,
            owner=owner,
            project_id=project_id,
            site_id=site_id,
            distance_m=request.distance_m,
        )
    except Exception as exc:
        raise _translate(exc) from exc
