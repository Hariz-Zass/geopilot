from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreateRequest, ProjectUpdateRequest
from app.services.isolation import ProjectScopeNotFoundError, resolve_project_scope


class ProjectNotFoundError(Exception):
    pass


def create_project(
    session: Session,
    *,
    owner: User,
    request: ProjectCreateRequest,
) -> Project:
    project = Project(
        owner_id=owner.id,
        name=request.name,
        description=request.description,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def list_projects(
    session: Session,
    *,
    owner: User,
    include_archived: bool = False,
) -> list[Project]:
    statement = select(Project).where(Project.owner_id == owner.id)
    if not include_archived:
        statement = statement.where(Project.is_archived.is_(False))
    statement = statement.order_by(Project.created_at.desc(), Project.id.desc())
    return list(session.scalars(statement))


def get_owned_project(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
) -> Project:
    try:
        return resolve_project_scope(
            session, owner=owner, project_id=project_id
        ).project
    except ProjectScopeNotFoundError as exc:
        # Preserve the public domain error while centralizing the ownership
        # boundary in the isolation service.
        raise ProjectNotFoundError from exc


def update_project(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    request: ProjectUpdateRequest,
) -> Project:
    project = get_owned_project(session, owner=owner, project_id=project_id)
    changes = request.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(project, field, value)
    session.commit()
    session.refresh(project)
    return project


def delete_project(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
) -> None:
    project = get_owned_project(session, owner=owner, project_id=project_id)
    session.delete(project)
    session.commit()
