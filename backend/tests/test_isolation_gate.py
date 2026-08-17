from __future__ import annotations

from collections.abc import Generator
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.project import Project
from app.models.site import Site
from app.models.user import User
from app.services.isolation import (
    ProjectScopeNotFoundError,
    ProjectState,
    ScopeStateError,
    SiteScopeNotFoundError,
    SiteState,
    resolve_analysis_scope,
    resolve_project_scope,
    resolve_site_scope,
)


@pytest.fixture()
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def register_spatial_passthrough(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        dbapi_connection.create_function("ST_GeomFromEWKT", 1, lambda value: value)
        dbapi_connection.create_function("ST_AsEWKT", 1, lambda value: value)

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _user(session: Session, email: str) -> User:
    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash="test-only-hash",
    )
    session.add(user)
    session.flush()
    return user


def _project(session: Session, owner: User, name: str, *, archived: bool = False) -> Project:
    project = Project(owner_id=owner.id, name=name, is_archived=archived)
    session.add(project)
    session.flush()
    return project


def _site(
    session: Session,
    project: Project,
    name: str,
    *,
    active: bool = True,
    archived: bool = False,
) -> Site:
    site = Site(
        project_id=project.id,
        name=name,
        geometry="SRID=4326;MULTIPOLYGON(((101 3,102 3,102 4,101 4,101 3)))",
        geometry_hash="a" * 64,
        geometry_revision=1,
        is_active=active,
        is_archived=archived,
    )
    session.add(site)
    session.flush()
    return site


def test_owned_project_resolves_but_cross_owner_is_indistinguishable_from_missing(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        owner = _user(session, "owner@example.com")
        stranger = _user(session, "stranger@example.com")
        project = _project(session, owner, "Private")
        session.commit()

        assert resolve_project_scope(session, owner=owner, project_id=project.id).project.id == project.id
        with pytest.raises(ProjectScopeNotFoundError):
            resolve_project_scope(session, owner=stranger, project_id=project.id)
        with pytest.raises(ProjectScopeNotFoundError):
            resolve_project_scope(session, owner=stranger, project_id=uuid.uuid4())


def test_archived_project_is_visible_for_audit_but_rejected_for_active_scope(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        owner = _user(session, "owner@example.com")
        project = _project(session, owner, "Archived", archived=True)
        session.commit()

        assert resolve_project_scope(session, owner=owner, project_id=project.id).project.is_archived
        with pytest.raises(ScopeStateError, match="project is archived"):
            resolve_project_scope(
                session,
                owner=owner,
                project_id=project.id,
                state=ProjectState.ACTIVE,
            )


def test_site_identifier_cannot_be_substituted_across_projects_even_for_same_owner(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        owner = _user(session, "owner@example.com")
        project_a = _project(session, owner, "A")
        project_b = _project(session, owner, "B")
        site_a = _site(session, project_a, "A site")
        session.commit()

        with pytest.raises(SiteScopeNotFoundError):
            resolve_site_scope(
                session,
                owner=owner,
                project_id=project_b.id,
                site_id=site_a.id,
            )


def test_site_identifier_cannot_be_substituted_through_foreign_owner_project(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        owner = _user(session, "owner@example.com")
        stranger = _user(session, "stranger@example.com")
        project = _project(session, owner, "Owner project")
        site = _site(session, project, "Target")
        session.commit()

        with pytest.raises(ProjectScopeNotFoundError):
            resolve_site_scope(
                session,
                owner=stranger,
                project_id=project.id,
                site_id=site.id,
            )


def test_available_scope_rejects_archived_site_but_allows_inactive_site(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        owner = _user(session, "owner@example.com")
        project = _project(session, owner, "P")
        inactive = _site(session, project, "Inactive", active=False)
        archived = _site(session, project, "Archived", active=False, archived=True)
        session.commit()

        assert resolve_site_scope(
            session,
            owner=owner,
            project_id=project.id,
            site_id=inactive.id,
            site_state=SiteState.AVAILABLE,
        ).site.id == inactive.id
        with pytest.raises(ScopeStateError, match="site is archived"):
            resolve_site_scope(
                session,
                owner=owner,
                project_id=project.id,
                site_id=archived.id,
                site_state=SiteState.AVAILABLE,
            )


def test_analysis_scope_requires_active_project_and_active_non_archived_site(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        owner = _user(session, "owner@example.com")
        project = _project(session, owner, "Analysis")
        active = _site(session, project, "Active", active=True)
        session.commit()

        scope = resolve_analysis_scope(
            session,
            owner=owner,
            project_id=project.id,
            site_id=active.id,
        )
        assert scope.project_id == project.id
        assert scope.site_id == active.id


def test_analysis_scope_rejects_inactive_site(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        owner = _user(session, "owner@example.com")
        project = _project(session, owner, "Analysis")
        site = _site(session, project, "Inactive", active=False)
        session.commit()

        with pytest.raises(ScopeStateError, match="site is inactive"):
            resolve_analysis_scope(
                session,
                owner=owner,
                project_id=project.id,
                site_id=site.id,
            )


def test_analysis_scope_rejects_archived_site_before_inactive_state(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        owner = _user(session, "owner@example.com")
        project = _project(session, owner, "Analysis")
        site = _site(session, project, "Archived", active=False, archived=True)
        session.commit()

        with pytest.raises(ScopeStateError, match="site is archived"):
            resolve_analysis_scope(
                session,
                owner=owner,
                project_id=project.id,
                site_id=site.id,
            )


def test_analysis_scope_rejects_archived_project_even_when_site_is_active(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        owner = _user(session, "owner@example.com")
        project = _project(session, owner, "Archived project", archived=True)
        site = _site(session, project, "Still marked active", active=True)
        session.commit()

        with pytest.raises(ScopeStateError, match="project is archived"):
            resolve_analysis_scope(
                session,
                owner=owner,
                project_id=project.id,
                site_id=site.id,
            )
