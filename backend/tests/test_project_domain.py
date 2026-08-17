from __future__ import annotations

from collections.abc import Generator
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db_session
from app.db.base import Base
from app.main import create_app
from app.models.project import Project


@pytest.fixture()
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as test_client:
        yield test_client


def _register_and_login(client: TestClient, email: str) -> str:
    password = "a-secure-password-123"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": email.split("@")[0], "password": password},
    )
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_projects_require_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_create_normalizes_project_and_sets_owner(client: TestClient) -> None:
    token = _register_and_login(client, "owner@example.com")
    me = client.get("/api/v1/auth/me", headers=_auth(token)).json()

    response = client.post(
        "/api/v1/projects",
        headers=_auth(token),
        json={"name": "  Meru   Planning  Study  ", "description": "  Pilot site  "},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Meru Planning Study"
    assert body["description"] == "Pilot site"
    assert body["owner_id"] == me["id"]
    assert body["is_archived"] is False


def test_list_is_strictly_owner_scoped(client: TestClient) -> None:
    owner_a = _register_and_login(client, "a@example.com")
    owner_b = _register_and_login(client, "b@example.com")

    created_a = client.post(
        "/api/v1/projects", headers=_auth(owner_a), json={"name": "A Project"}
    )
    created_b = client.post(
        "/api/v1/projects", headers=_auth(owner_b), json={"name": "B Project"}
    )
    assert created_a.status_code == 201
    assert created_b.status_code == 201

    list_a = client.get("/api/v1/projects", headers=_auth(owner_a))
    assert list_a.status_code == 200
    assert [item["name"] for item in list_a.json()] == ["A Project"]

    list_b = client.get("/api/v1/projects", headers=_auth(owner_b))
    assert [item["name"] for item in list_b.json()] == ["B Project"]


def test_cross_owner_get_update_delete_are_indistinguishable_from_missing(
    client: TestClient,
) -> None:
    owner = _register_and_login(client, "owner@example.com")
    stranger = _register_and_login(client, "stranger@example.com")
    project_id = client.post(
        "/api/v1/projects", headers=_auth(owner), json={"name": "Private"}
    ).json()["id"]

    responses = [
        client.get(f"/api/v1/projects/{project_id}", headers=_auth(stranger)),
        client.patch(
            f"/api/v1/projects/{project_id}",
            headers=_auth(stranger),
            json={"name": "Stolen"},
        ),
        client.delete(f"/api/v1/projects/{project_id}", headers=_auth(stranger)),
        client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000001",
            headers=_auth(stranger),
        ),
    ]
    for response in responses:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "project_not_found"

    still_there = client.get(f"/api/v1/projects/{project_id}", headers=_auth(owner))
    assert still_there.status_code == 200
    assert still_there.json()["name"] == "Private"


def test_update_archive_and_archive_filtering(client: TestClient) -> None:
    token = _register_and_login(client, "owner@example.com")
    project = client.post(
        "/api/v1/projects",
        headers=_auth(token),
        json={"name": "Draft", "description": "old"},
    ).json()

    updated = client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=_auth(token),
        json={"name": "Final Project", "description": "  revised  ", "is_archived": True},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Final Project"
    assert updated.json()["description"] == "revised"
    assert updated.json()["is_archived"] is True

    default_list = client.get("/api/v1/projects", headers=_auth(token))
    assert default_list.json() == []

    audit_list = client.get(
        "/api/v1/projects?include_archived=true", headers=_auth(token)
    )
    assert len(audit_list.json()) == 1
    assert audit_list.json()[0]["id"] == project["id"]

    direct = client.get(f"/api/v1/projects/{project['id']}", headers=_auth(token))
    assert direct.status_code == 200


def test_delete_owned_project_removes_it(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    token = _register_and_login(client, "owner@example.com")
    project_id = client.post(
        "/api/v1/projects", headers=_auth(token), json={"name": "Disposable"}
    ).json()["id"]

    response = client.delete(f"/api/v1/projects/{project_id}", headers=_auth(token))
    assert response.status_code == 204
    assert response.content == b""

    missing = client.get(f"/api/v1/projects/{project_id}", headers=_auth(token))
    assert missing.status_code == 404
    with session_factory() as session:
        assert session.scalar(select(Project).where(Project.id == uuid.UUID(project_id))) is None


def test_blank_name_is_rejected(client: TestClient) -> None:
    token = _register_and_login(client, "owner@example.com")
    response = client.post(
        "/api/v1/projects", headers=_auth(token), json={"name": "    "}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
