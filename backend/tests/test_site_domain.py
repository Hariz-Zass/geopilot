from __future__ import annotations

from collections.abc import Generator
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db_session
from app.db.base import Base
from app.main import create_app
from app.models.site import Site


SQUARE = {
    "type": "Polygon",
    "coordinates": [[[101.70, 3.00], [101.71, 3.00], [101.71, 3.01], [101.70, 3.01], [101.70, 3.00]]],
}
SQUARE_2 = {
    "type": "Polygon",
    "coordinates": [[[101.72, 3.00], [101.73, 3.00], [101.73, 3.01], [101.72, 3.01], [101.72, 3.00]]],
}


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
    assert client.post("/api/v1/auth/register", json={"email": email, "display_name": email.split("@")[0], "password": password}).status_code == 201
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _project(client: TestClient, token: str, name: str = "Spatial Project") -> dict[str, object]:
    response = client.post("/api/v1/projects", headers=_auth(token), json={"name": name})
    assert response.status_code == 201
    return response.json()


def _site(client: TestClient, token: str, project_id: str, name: str = "Target Site", geometry=SQUARE, is_active: bool = True):
    return client.post(
        f"/api/v1/projects/{project_id}/sites",
        headers=_auth(token),
        json={"name": name, "geometry": geometry, "is_active": is_active},
    )


def test_sites_require_authentication(client: TestClient) -> None:
    project_id = uuid.uuid4()
    response = client.get(f"/api/v1/projects/{project_id}/sites")
    assert response.status_code == 401


def test_create_polygon_is_canonicalized_and_spatial_identity_is_returned(client: TestClient) -> None:
    token = _register_and_login(client, "owner@example.com")
    project = _project(client, token)
    response = _site(client, token, project["id"])
    assert response.status_code == 201
    body = response.json()
    assert body["project_id"] == project["id"]
    assert body["geometry"]["type"] == "MultiPolygon"
    assert body["geometry"]["coordinates"][0] == SQUARE["coordinates"]
    assert len(body["geometry_hash"]) == 64
    assert body["geometry_revision"] == 1
    assert body["is_active"] is True
    assert body["is_archived"] is False


def test_cross_owner_project_boundary_hides_sites(client: TestClient) -> None:
    owner = _register_and_login(client, "owner@example.com")
    stranger = _register_and_login(client, "stranger@example.com")
    project = _project(client, owner)
    site = _site(client, owner, project["id"]).json()

    responses = [
        client.get(f"/api/v1/projects/{project['id']}/sites", headers=_auth(stranger)),
        client.get(f"/api/v1/projects/{project['id']}/sites/{site['id']}", headers=_auth(stranger)),
        client.patch(f"/api/v1/projects/{project['id']}/sites/{site['id']}", headers=_auth(stranger), json={"name": "Probe"}),
        client.delete(f"/api/v1/projects/{project['id']}/sites/{site['id']}", headers=_auth(stranger)),
    ]
    for response in responses:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "project_not_found"


def test_site_id_from_another_owned_project_is_hidden_as_site_not_found(client: TestClient) -> None:
    token = _register_and_login(client, "owner@example.com")
    project_a = _project(client, token, "A")
    project_b = _project(client, token, "B")
    site = _site(client, token, project_a["id"]).json()
    response = client.get(f"/api/v1/projects/{project_b['id']}/sites/{site['id']}", headers=_auth(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "site_not_found"


def test_only_one_active_site_per_project(client: TestClient) -> None:
    token = _register_and_login(client, "owner@example.com")
    project = _project(client, token)
    first = _site(client, token, project["id"], name="First").json()
    second = _site(client, token, project["id"], name="Second", geometry=SQUARE_2).json()
    listed = client.get(f"/api/v1/projects/{project['id']}/sites", headers=_auth(token)).json()
    by_id = {item["id"]: item for item in listed}
    assert by_id[first["id"]]["is_active"] is False
    assert by_id[second["id"]]["is_active"] is True


def test_activation_switches_active_site(client: TestClient) -> None:
    token = _register_and_login(client, "owner@example.com")
    project = _project(client, token)
    first = _site(client, token, project["id"], name="First").json()
    second = _site(client, token, project["id"], name="Second", geometry=SQUARE_2, is_active=False).json()
    assert first["is_active"] is True and second["is_active"] is False
    activated = client.patch(f"/api/v1/projects/{project['id']}/sites/{second['id']}", headers=_auth(token), json={"is_active": True})
    assert activated.status_code == 200
    first_now = client.get(f"/api/v1/projects/{project['id']}/sites/{first['id']}", headers=_auth(token)).json()
    assert first_now["is_active"] is False
    assert activated.json()["is_active"] is True


def test_geometry_revision_changes_only_for_new_geometry(client: TestClient) -> None:
    token = _register_and_login(client, "owner@example.com")
    project = _project(client, token)
    site = _site(client, token, project["id"]).json()
    same = client.patch(f"/api/v1/projects/{project['id']}/sites/{site['id']}", headers=_auth(token), json={"geometry": SQUARE})
    assert same.status_code == 200
    assert same.json()["geometry_revision"] == 1
    assert same.json()["geometry_hash"] == site["geometry_hash"]

    changed = client.patch(f"/api/v1/projects/{project['id']}/sites/{site['id']}", headers=_auth(token), json={"geometry": SQUARE_2})
    assert changed.status_code == 200
    assert changed.json()["geometry_revision"] == 2
    assert changed.json()["geometry_hash"] != site["geometry_hash"]


def test_archiving_active_site_deactivates_and_filtering_is_explicit(client: TestClient) -> None:
    token = _register_and_login(client, "owner@example.com")
    project = _project(client, token)
    site = _site(client, token, project["id"]).json()
    archived = client.patch(f"/api/v1/projects/{project['id']}/sites/{site['id']}", headers=_auth(token), json={"is_archived": True})
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True
    assert archived.json()["is_active"] is False
    assert client.get(f"/api/v1/projects/{project['id']}/sites", headers=_auth(token)).json() == []
    audit = client.get(f"/api/v1/projects/{project['id']}/sites?include_archived=true", headers=_auth(token)).json()
    assert len(audit) == 1


def test_archived_site_cannot_be_activated_without_restore(client: TestClient) -> None:
    token = _register_and_login(client, "owner@example.com")
    project = _project(client, token)
    site = _site(client, token, project["id"]).json()
    client.patch(f"/api/v1/projects/{project['id']}/sites/{site['id']}", headers=_auth(token), json={"is_archived": True})
    response = client.patch(f"/api/v1/projects/{project['id']}/sites/{site['id']}", headers=_auth(token), json={"is_active": True})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "site_state_invalid"


def test_archived_project_rejects_new_site(client: TestClient) -> None:
    token = _register_and_login(client, "owner@example.com")
    project = _project(client, token)
    assert client.patch(f"/api/v1/projects/{project['id']}", headers=_auth(token), json={"is_archived": True}).status_code == 200
    response = _site(client, token, project["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "site_state_invalid"


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Polygon", "coordinates": [[[101.7, 3.0], [101.71, 3.0], [101.71, 3.01], [101.7, 3.01]]]},
        {"type": "Polygon", "coordinates": [[[181.0, 3.0], [181.1, 3.0], [181.1, 3.1], [181.0, 3.1], [181.0, 3.0]]]},
        {"type": "Polygon", "coordinates": [[[0.0, 0.0], [1.0, 1.0], [0.0, 1.0], [1.0, 0.0], [0.0, 0.0]]]},
    ],
)
def test_invalid_geometry_is_rejected(client: TestClient, geometry: dict[str, object]) -> None:
    token = _register_and_login(client, f"owner-{uuid.uuid4()}@example.com")
    project = _project(client, token)
    response = _site(client, token, project["id"], geometry=geometry)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_delete_site_removes_owned_record(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    token = _register_and_login(client, "delete@example.com")
    project = _project(client, token)
    site_id = _site(client, token, project["id"]).json()["id"]
    response = client.delete(f"/api/v1/projects/{project['id']}/sites/{site_id}", headers=_auth(token))
    assert response.status_code == 204
    with session_factory() as session:
        assert session.scalar(select(Site).where(Site.id == uuid.UUID(site_id))) is None
