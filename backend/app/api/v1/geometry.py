from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.geometry_reference import GeometryResolveRequest, GeometryResolution
from app.services.geometry_references import (
    GeometryReferenceNotFoundError,
    GeometryReferenceStaleError,
    GeometryReferenceStateError,
    GeometryResolutionError,
    resolve_geometry_reference,
)
from app.services.isolation import ProjectScopeNotFoundError, ScopeStateError, SiteScopeNotFoundError

router = APIRouter(prefix="/projects/{project_id}/geometry", tags=["geometry"])


@router.post("/resolve", response_model=GeometryResolution)
def resolve_geometry(
    project_id: uuid.UUID,
    request: GeometryResolveRequest,
    session: Session = Depends(get_db_session),
    owner: User = Depends(get_current_user),
) -> GeometryResolution:
    try:
        return resolve_geometry_reference(
            session,
            owner=owner,
            project_id=project_id,
            reference=request.reference,
        )
    except (ProjectScopeNotFoundError, SiteScopeNotFoundError, GeometryReferenceNotFoundError) as exc:
        raise AppError(
            status_code=404,
            code="geometry_reference_not_found",
            message="Geometry reference was not found in the authorized project scope",
        ) from exc
    except GeometryReferenceStaleError as exc:
        raise AppError(
            status_code=409,
            code="geometry_reference_stale",
            message="Geometry reference no longer matches the current authoritative geometry",
        ) from exc
    except (ScopeStateError, GeometryReferenceStateError) as exc:
        raise AppError(
            status_code=409,
            code="geometry_reference_unavailable",
            message=str(exc) or "Geometry source is not currently available",
        ) from exc
    except GeometryResolutionError as exc:
        raise AppError(
            status_code=503,
            code="geometry_resolution_invalid",
            message="Authoritative geometry could not be resolved safely",
        ) from exc
