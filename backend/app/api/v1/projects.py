from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.project import ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest
from app.services.projects import (
    ProjectNotFoundError,
    create_project,
    delete_project,
    get_owned_project,
    list_projects,
    update_project,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _not_found(exc: ProjectNotFoundError) -> AppError:
    return AppError(
        code="project_not_found",
        message="Project not found.",
        status_code=404,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create(
    payload: ProjectCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ProjectResponse:
    project = create_project(session, owner=current_user, request=payload)
    return ProjectResponse.model_validate(project)


@router.get("", response_model=list[ProjectResponse])
def list_owned(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    include_archived: Annotated[bool, Query()] = False,
) -> list[ProjectResponse]:
    return [
        ProjectResponse.model_validate(project)
        for project in list_projects(
            session,
            owner=current_user,
            include_archived=include_archived,
        )
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_one(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ProjectResponse:
    try:
        project = get_owned_project(session, owner=current_user, project_id=project_id)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ProjectResponse:
    try:
        project = update_project(
            session,
            owner=current_user,
            project_id=project_id,
            request=payload,
        )
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> Response:
    try:
        delete_project(session, owner=current_user, project_id=project_id)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
