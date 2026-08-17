from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.site import Site
from app.models.user import User
from app.schemas.site import (
    SiteCreateRequest,
    canonical_multipolygon,
    geometry_digest,
    multipolygon_to_ewkt,
)
from app.services.projects import get_owned_project
from app.services.sites import SiteStateError

# SMART_ORGANIZER_PHASE2C1_TRANSACTIONAL_SITE


class DuplicateCompetitionSiteError(Exception):
    pass


@dataclass(frozen=True)
class TransactionalSiteResult:
    site: Site
    created: bool
    duplicate: bool


def create_competition_site_uncommitted(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    request: SiteCreateRequest,
) -> TransactionalSiteResult:
    """
    Create a competition Site inside the caller's transaction.

    Contract:
    - never commits;
    - duplicate protection is project_id + canonical geometry_hash;
    - active-site lifecycle matches the existing Site service;
    - caller owns commit/rollback.
    """
    project = get_owned_project(session, owner=owner, project_id=project_id)
    if project.is_archived:
        raise SiteStateError("cannot create a site in an archived project")

    coords = canonical_multipolygon(request.geometry)
    digest = geometry_digest(coords)

    existing = session.scalar(
        select(Site).where(
            Site.project_id == project.id,
            Site.geometry_hash == digest,
            Site.is_archived.is_(False),
        )
    )
    if existing is not None:
        return TransactionalSiteResult(
            site=existing,
            created=False,
            duplicate=True,
        )

    if request.is_active:
        session.execute(
            update(Site)
            .where(
                Site.project_id == project.id,
                Site.is_active.is_(True),
            )
            .values(is_active=False)
        )

    site = Site(
        project_id=project.id,
        name=request.name,
        geometry=multipolygon_to_ewkt(coords),
        geometry_hash=digest,
        geometry_revision=1,
        is_active=request.is_active,
        is_archived=False,
    )
    session.add(site)
    session.flush()

    return TransactionalSiteResult(
        site=site,
        created=True,
        duplicate=False,
    )
