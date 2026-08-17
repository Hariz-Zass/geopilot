from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db_session
from app.db.base import Base
from app.main import create_app

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[101.70, 3.00], [101.71, 3.00], [101.71, 3.01], [101.70, 3.01], [101.70, 3.00]]],
}


@pytest.fixture()
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def spatial_passthrough(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        dbapi_connection.create_function("ST_GeomFromEWKT", 1, lambda value: value)
        dbapi_connection.create_function("ST_AsEWKT", 1, lambda value: value)

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
    with TestClient(app) as value:
        yield value


def token(client: TestClient, email: str = "map-owner@example.com") -> str:
    password = "a-secure-password-123"
    assert client.post("/api/v1/auth/register", json={"email": email, "display_name": "Map Owner", "password": password}).status_code == 201
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]


def auth(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def test_active_site_endpoint_returns_server_designated_active_geometry(client: TestClient) -> None:
    bearer = token(client)
    project = client.post("/api/v1/projects", headers=auth(bearer), json={"name": "Map Project"}).json()
    first = client.post(f"/api/v1/projects/{project['id']}/sites", headers=auth(bearer), json={"name": "First", "geometry": SQUARE, "is_active": True}).json()
    assert first["is_active"] is True

    response = client.get(f"/api/v1/projects/{project['id']}/sites/active", headers=auth(bearer))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == first["id"]
    assert body["geometry"]["type"] == "MultiPolygon"
    assert body["geometry_hash"] == first["geometry_hash"]


def test_active_site_endpoint_fails_closed_when_no_active_site(client: TestClient) -> None:
    bearer = token(client)
    project = client.post("/api/v1/projects", headers=auth(bearer), json={"name": "No Active"}).json()
    client.post(f"/api/v1/projects/{project['id']}/sites", headers=auth(bearer), json={"name": "Inactive", "geometry": SQUARE, "is_active": False})
    response = client.get(f"/api/v1/projects/{project['id']}/sites/active", headers=auth(bearer))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "site_not_found"


def test_active_site_endpoint_hides_foreign_project(client: TestClient) -> None:
    owner = token(client, "owner-map@example.com")
    outsider = token(client, "outsider-map@example.com")
    project = client.post("/api/v1/projects", headers=auth(owner), json={"name": "Private Map"}).json()
    response = client.get(f"/api/v1/projects/{project['id']}/sites/active", headers=auth(outsider))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"
