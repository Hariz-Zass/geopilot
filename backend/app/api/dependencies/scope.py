from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.services.isolation import (
    ProjectScopeNotFoundError,
    ScopeStateError,
    SiteScope,
    SiteScopeNotFoundError,
    resolve_analysis_scope,
)


def get_analysis_scope(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> SiteScope:
    """FastAPI dependency for future evidence-producing analytical routes."""

    try:
        return resolve_analysis_scope(
            session,
            owner=current_user,
            project_id=project_id,
            site_id=site_id,
        )
    except ProjectScopeNotFoundError as exc:
        raise AppError(
            code="project_not_found",
            message="Project not found.",
            status_code=404,
        ) from exc
    except SiteScopeNotFoundError as exc:
        raise AppError(
            code="site_not_found",
            message="Site not found.",
            status_code=404,
        ) from exc
    except ScopeStateError as exc:
        raise AppError(
            code="analysis_scope_invalid",
            message=str(exc),
            status_code=409,
        ) from exc
