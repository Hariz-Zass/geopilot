from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.site import Site
from app.models.user import User


class ProjectScopeNotFoundError(Exception):
    """Project is absent or not owned by the authenticated user."""


class SiteScopeNotFoundError(Exception):
    """Site is absent from the already-authorized project."""


class ScopeStateError(Exception):
    """A resource exists in scope but is not eligible for the requested operation."""


class ProjectState(str, Enum):
    ANY = "any"
    ACTIVE = "active"


class SiteState(str, Enum):
    ANY = "any"
    AVAILABLE = "available"
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class ProjectScope:
    project: Project

    @property
    def project_id(self) -> uuid.UUID:
        return self.project.id


@dataclass(frozen=True, slots=True)
class SiteScope:
    project: Project
    site: Site

    @property
    def project_id(self) -> uuid.UUID:
        return self.project.id

    @property
    def site_id(self) -> uuid.UUID:
        return self.site.id


def resolve_project_scope(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    state: ProjectState = ProjectState.ANY,
) -> ProjectScope:
    """Resolve a project strictly through the authenticated owner boundary.

    A project owned by another user is deliberately indistinguishable from a
    missing project. State eligibility is checked only after ownership has
    already been proven.
    """

    project = session.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == owner.id,
        )
    )
    if project is None:
        raise ProjectScopeNotFoundError

    if state is ProjectState.ACTIVE and project.is_archived:
        raise ScopeStateError("project is archived")

    return ProjectScope(project=project)


def resolve_site_scope(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    project_state: ProjectState = ProjectState.ANY,
    site_state: SiteState = SiteState.ANY,
) -> SiteScope:
    """Resolve a site only after resolving the owned parent project.

    The site query always includes both ``site_id`` and ``project_id``. This is
    intentional: a valid site identifier must never be reusable under another
    project, even when both projects belong to the same user.
    """

    project_scope = resolve_project_scope(
        session,
        owner=owner,
        project_id=project_id,
        state=project_state,
    )

    site = session.scalar(
        select(Site).where(
            Site.id == site_id,
            Site.project_id == project_scope.project.id,
        )
    )
    if site is None:
        raise SiteScopeNotFoundError

    if site_state in {SiteState.AVAILABLE, SiteState.ACTIVE} and site.is_archived:
        raise ScopeStateError("site is archived")
    if site_state is SiteState.ACTIVE and not site.is_active:
        raise ScopeStateError("site is inactive")

    return SiteScope(project=project_scope.project, site=site)


def resolve_analysis_scope(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> SiteScope:
    """Resolve the canonical scope for deterministic/AI analytical execution.

    Analysis is fail-closed: archived projects, archived sites, and inactive
    sites are not valid analytical targets. Future evidence-producing domains
    should enter through this boundary (or an equally strict domain-specific
    derivative) before reading or creating project/site evidence.
    """

    return resolve_site_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        project_state=ProjectState.ACTIVE,
        site_state=site_state,
    )
