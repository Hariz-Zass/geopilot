from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.site import Site
from app.models.user import User
from app.schemas.site import (
    SiteCreateRequest,
    SiteUpdateRequest,
    canonical_multipolygon,
    ewkt_to_geojson,
    geometry_digest,
    multipolygon_to_ewkt,
)
from app.services.projects import ProjectNotFoundError, get_owned_project
from app.services.isolation import (
    ProjectScopeNotFoundError,
    SiteScopeNotFoundError,
    resolve_site_scope,
)


class SiteNotFoundError(Exception):
    pass


class SiteStateError(Exception):
    pass


def _deactivate_project_sites(session: Session, project_id: uuid.UUID, *, except_id: uuid.UUID | None = None) -> None:
    stmt = update(Site).where(Site.project_id == project_id, Site.is_active.is_(True))
    if except_id is not None:
        stmt = stmt.where(Site.id != except_id)
    session.execute(stmt.values(is_active=False))


def create_site(session: Session, *, owner: User, project_id: uuid.UUID, request: SiteCreateRequest) -> Site:
    project = get_owned_project(session, owner=owner, project_id=project_id)
    if project.is_archived:
        raise SiteStateError("cannot create a site in an archived project")
    coords = canonical_multipolygon(request.geometry)
    if request.is_active:
        _deactivate_project_sites(session, project.id)
    site = Site(
        project_id=project.id,
        name=request.name,
        geometry=multipolygon_to_ewkt(coords),
        geometry_hash=geometry_digest(coords),
        geometry_revision=1,
        is_active=request.is_active,
        is_archived=False,
    )
    session.add(site)
    session.commit()
    session.refresh(site)
    return site


def list_sites(session: Session, *, owner: User, project_id: uuid.UUID, include_archived: bool = False) -> list[Site]:
    get_owned_project(session, owner=owner, project_id=project_id)
    stmt = select(Site).where(Site.project_id == project_id)
    if not include_archived:
        stmt = stmt.where(Site.is_archived.is_(False))
    stmt = stmt.order_by(Site.is_active.desc(), Site.created_at.desc(), Site.id.desc())
    return list(session.scalars(stmt))



def get_active_site(session: Session, *, owner: User, project_id: uuid.UUID) -> Site:
    """Return the one server-designated active, non-archived Site for an owned Project."""
    project = get_owned_project(session, owner=owner, project_id=project_id)
    if project.is_archived:
        raise SiteNotFoundError
    stmt = select(Site).where(
        Site.project_id == project.id,
        Site.is_active.is_(True),
        Site.is_archived.is_(False),
    )
    site = session.scalar(stmt)
    if site is None:
        raise SiteNotFoundError
    return site

def get_owned_site(session: Session, *, owner: User, project_id: uuid.UUID, site_id: uuid.UUID) -> Site:
    try:
        return resolve_site_scope(
            session,
            owner=owner,
            project_id=project_id,
            site_id=site_id,
        ).site
    except ProjectScopeNotFoundError as exc:
        raise ProjectNotFoundError from exc
    except SiteScopeNotFoundError as exc:
        raise SiteNotFoundError from exc


def update_site(session: Session, *, owner: User, project_id: uuid.UUID, site_id: uuid.UUID, request: SiteUpdateRequest) -> Site:
    site = get_owned_site(session, owner=owner, project_id=project_id, site_id=site_id)
    changes = request.model_dump(exclude_unset=True, exclude={"geometry"})

    target_archived = changes.get("is_archived", site.is_archived)
    target_active = changes.get("is_active", site.is_active)
    if target_archived and target_active:
        # Archiving an active site automatically deactivates it unless the
        # caller explicitly attempts the contradictory active+archived state.
        if request.is_archived is True and request.is_active is None:
            changes["is_active"] = False
            target_active = False
        else:
            raise SiteStateError("an archived site cannot be active")
    if request.is_active is True and site.is_archived and request.is_archived is not False:
        raise SiteStateError("an archived site must be restored before activation")

    if target_active:
        _deactivate_project_sites(session, project_id, except_id=site.id)

    if request.geometry is not None:
        coords = canonical_multipolygon(request.geometry)
        digest = geometry_digest(coords)
        if digest != site.geometry_hash:
            site.geometry = multipolygon_to_ewkt(coords)
            site.geometry_hash = digest
            site.geometry_revision += 1

    for field, value in changes.items():
        setattr(site, field, value)
    session.commit()
    session.refresh(site)
    return site


def delete_site(session: Session, *, owner: User, project_id: uuid.UUID, site_id: uuid.UUID) -> None:
    site = get_owned_site(session, owner=owner, project_id=project_id, site_id=site_id)
    session.delete(site)
    session.commit()


def site_to_api(site: Site) -> dict[str, object]:
    return {
        "id": site.id,
        "project_id": site.project_id,
        "name": site.name,
        "geometry": ewkt_to_geojson(site.geometry),
        "geometry_hash": site.geometry_hash,
        "geometry_revision": site.geometry_revision,
        "is_active": site.is_active,
        "is_archived": site.is_archived,
        "created_at": site.created_at,
        "updated_at": site.updated_at,
    }
