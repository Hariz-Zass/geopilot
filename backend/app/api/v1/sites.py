from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.site import SiteCreateRequest, SiteResponse, SiteUpdateRequest
from app.services.projects import ProjectNotFoundError
from app.services.sites import (
    SiteNotFoundError,
    SiteStateError,
    create_site,
    delete_site,
    get_active_site,
    get_owned_site,
    list_sites,
    site_to_api,
    update_site,
)

router = APIRouter(prefix="/projects/{project_id}/sites", tags=["sites"])


def _project_not_found() -> AppError:
    return AppError(code="project_not_found", message="Project not found.", status_code=404)


def _site_not_found() -> AppError:
    return AppError(code="site_not_found", message="Site not found.", status_code=404)


def _state_error(exc: SiteStateError) -> AppError:
    return AppError(code="site_state_invalid", message=str(exc), status_code=409)


@router.post("", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create(project_id: uuid.UUID, payload: SiteCreateRequest, current_user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> SiteResponse:
    try:
        site = create_site(session, owner=current_user, project_id=project_id, request=payload)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except SiteStateError as exc:
        raise _state_error(exc) from exc
    return SiteResponse.model_validate(site_to_api(site))


@router.get("", response_model=list[SiteResponse])
def list_owned(project_id: uuid.UUID, current_user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)], include_archived: Annotated[bool, Query()] = False) -> list[SiteResponse]:
    try:
        sites = list_sites(session, owner=current_user, project_id=project_id, include_archived=include_archived)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    return [SiteResponse.model_validate(site_to_api(site)) for site in sites]


@router.get("/active", response_model=SiteResponse)
def get_active(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> SiteResponse:
    try:
        site = get_active_site(session, owner=current_user, project_id=project_id)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except SiteNotFoundError as exc:
        raise _site_not_found() from exc
    return SiteResponse.model_validate(site_to_api(site))


@router.get("/{site_id}", response_model=SiteResponse)
def get_one(project_id: uuid.UUID, site_id: uuid.UUID, current_user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> SiteResponse:
    try:
        site = get_owned_site(session, owner=current_user, project_id=project_id, site_id=site_id)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except SiteNotFoundError as exc:
        raise _site_not_found() from exc
    return SiteResponse.model_validate(site_to_api(site))


@router.patch("/{site_id}", response_model=SiteResponse)
def update(project_id: uuid.UUID, site_id: uuid.UUID, payload: SiteUpdateRequest, current_user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> SiteResponse:
    try:
        site = update_site(session, owner=current_user, project_id=project_id, site_id=site_id, request=payload)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except SiteNotFoundError as exc:
        raise _site_not_found() from exc
    except SiteStateError as exc:
        raise _state_error(exc) from exc
    return SiteResponse.model_validate(site_to_api(site))


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(project_id: uuid.UUID, site_id: uuid.UUID, current_user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> Response:
    try:
        delete_site(session, owner=current_user, project_id=project_id, site_id=site_id)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except SiteNotFoundError as exc:
        raise _site_not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
