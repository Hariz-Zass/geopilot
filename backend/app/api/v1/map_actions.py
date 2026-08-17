from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.map_action import MapActionResolveRequest, ResolvedMapAction
from app.services.geometry_references import (
    GeometryReferenceNotFoundError,
    GeometryReferenceStaleError,
    GeometryReferenceStateError,
    GeometryResolutionError,
)
from app.services.isolation import ProjectScopeNotFoundError, ScopeStateError, SiteScopeNotFoundError
from app.services.map_actions import MapActionResolutionError, resolve_map_action

router = APIRouter(prefix="/projects/{project_id}/map-actions", tags=["map-actions"])


@router.post("/resolve", response_model=ResolvedMapAction)
def resolve_project_map_action(
    project_id: uuid.UUID,
    request: MapActionResolveRequest,
    session: Session = Depends(get_db_session),
    owner: User = Depends(get_current_user),
) -> ResolvedMapAction:
    try:
        return resolve_map_action(
            session,
            owner=owner,
            project_id=project_id,
            map_action=request.map_action,
        )
    except (ProjectScopeNotFoundError, SiteScopeNotFoundError, GeometryReferenceNotFoundError) as exc:
        raise AppError(
            status_code=404,
            code="map_action_geometry_not_found",
            message="Map action geometry was not found in the authorized project scope",
        ) from exc
    except GeometryReferenceStaleError as exc:
        raise AppError(
            status_code=409,
            code="map_action_geometry_stale",
            message="Map action contains a stale geometry reference",
        ) from exc
    except (ScopeStateError, GeometryReferenceStateError) as exc:
        raise AppError(
            status_code=409,
            code="map_action_geometry_unavailable",
            message=str(exc) or "Map action geometry is not currently available",
        ) from exc
    except (GeometryResolutionError, MapActionResolutionError) as exc:
        raise AppError(
            status_code=503,
            code="map_action_resolution_invalid",
            message="Map action could not be resolved safely",
        ) from exc
