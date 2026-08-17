from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db_session
from app.db.base import Base
from app.main import create_app


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
def client(session_factory):
    app = create_app()

    def override():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, email: str) -> str:
    password = "a-secure-password-123"
    client.post("/api/v1/auth/register", json={"email": email, "display_name": "u", "password": password})
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]


def h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def project(client: TestClient, token: str, name: str = "P") -> str:
    return client.post("/api/v1/projects", headers=h(token), json={"name": name}).json()["id"]


def payload(checksum: str = "a" * 64) -> dict:
    return {
        "title": "  Rancangan Tempatan Example  ",
        "description": " controlled planning source ",
        "document_class": "RT",
        "authority": "  PLANMalaysia Example  ",
        "jurisdiction": " Example District ",
        "geographic_applicability": {"country": "MY", "state": "Example"},
        "initial_version": {
            "version_label": "Gazetted 2035",
            "publication_year": 2035,
            "source_kind": "upload",
            "source_filename": "rt-example.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 12345,
            "checksum_sha256": checksum,
            "provenance": {"supplied_by": "project_owner"},
        },
    }


def test_requires_auth(client):
    response = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000001/documents")
    assert response.status_code == 401


def test_create_document_and_initial_immutable_version(client):
    token = login(client, "a@example.com")
    project_id = project(client, token)
    response = client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=payload())
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Rancangan Tempatan Example"
    assert body["description"] == "controlled planning source"
    assert body["authority"] == "PLANMalaysia Example"
    assert body["document_class"] == "RT"
    assert body["geographic_applicability"]["country"] == "MY"

    versions = client.get(f"/api/v1/projects/{project_id}/documents/{body['id']}/versions", headers=h(token))
    assert versions.status_code == 200
    version = versions.json()[0]
    assert version["version_sequence"] == 1
    assert version["checksum_sha256"] == "a" * 64
    assert version["source_filename"] == "rt-example.pdf"
    assert version["extraction_state"] == "pending"
    assert version["index_state"] == "pending"


def test_controlled_document_class_and_source_validation(client):
    token = login(client, "a@example.com")
    project_id = project(client, token)
    bad_class = payload()
    bad_class["document_class"] = "MADE_UP"
    assert client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=bad_class).status_code == 422

    missing_filename = payload()
    missing_filename["initial_version"]["source_filename"] = None
    assert client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=missing_filename).status_code == 422

    acquired = payload()
    acquired["initial_version"].update(source_kind="acquired", source_filename=None, source_uri=None)
    assert client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=acquired).status_code == 422


def test_publication_date_and_year_must_agree(client):
    token = login(client, "a@example.com")
    project_id = project(client, token)
    data = payload()
    data["initial_version"].update(publication_year=2035, publication_date="2036-01-01")
    assert client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=data).status_code == 422


def test_create_second_version_and_duplicate_checksum_rejected(client):
    token = login(client, "a@example.com")
    project_id = project(client, token)
    document_id = client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=payload()).json()["id"]

    second = payload("b" * 64)["initial_version"]
    second["version_label"] = "Amendment 1"
    response = client.post(
        f"/api/v1/projects/{project_id}/documents/{document_id}/versions",
        headers=h(token),
        json=second,
    )
    assert response.status_code == 201
    assert response.json()["version_sequence"] == 2

    duplicate = payload()["initial_version"]
    response = client.post(
        f"/api/v1/projects/{project_id}/documents/{document_id}/versions",
        headers=h(token),
        json=duplicate,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_version_conflict"


def test_document_version_source_fields_have_no_patch_or_delete_api(client):
    token = login(client, "a@example.com")
    project_id = project(client, token)
    document_id = client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=payload()).json()["id"]
    version_id = client.get(f"/api/v1/projects/{project_id}/documents/{document_id}/versions", headers=h(token)).json()[0]["id"]
    endpoint = f"/api/v1/projects/{project_id}/documents/{document_id}/versions/{version_id}"
    assert client.patch(endpoint, headers=h(token), json={"checksum_sha256": "b" * 64}).status_code == 405
    assert client.delete(endpoint, headers=h(token)).status_code == 405


def test_document_metadata_update_cannot_modify_controlled_class_or_authority(client):
    token = login(client, "a@example.com")
    project_id = project(client, token)
    document_id = client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=payload()).json()["id"]
    response = client.patch(
        f"/api/v1/projects/{project_id}/documents/{document_id}",
        headers=h(token),
        json={"authority": "Changed", "document_class": "RFN"},
    )
    assert response.status_code == 422


def test_cross_owner_and_cross_project_document_substitution_fail_closed(client):
    a = login(client, "a@example.com")
    b = login(client, "b@example.com")
    pa = project(client, a, "A")
    pa2 = project(client, a, "A2")
    document_id = client.post(f"/api/v1/projects/{pa}/documents", headers=h(a), json=payload()).json()["id"]

    assert client.get(f"/api/v1/projects/{pa}/documents/{document_id}", headers=h(b)).status_code == 404
    response = client.get(f"/api/v1/projects/{pa2}/documents/{document_id}", headers=h(a))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "planning_document_not_found"


def test_archived_document_hidden_by_default_and_cannot_receive_versions(client):
    token = login(client, "a@example.com")
    project_id = project(client, token)
    document_id = client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=payload()).json()["id"]
    archived = client.patch(
        f"/api/v1/projects/{project_id}/documents/{document_id}",
        headers=h(token),
        json={"is_archived": True},
    )
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True
    assert client.get(f"/api/v1/projects/{project_id}/documents", headers=h(token)).json() == []
    assert len(client.get(f"/api/v1/projects/{project_id}/documents?include_archived=true", headers=h(token)).json()) == 1

    response = client.post(
        f"/api/v1/projects/{project_id}/documents/{document_id}/versions",
        headers=h(token),
        json=payload("b" * 64)["initial_version"],
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "planning_document_state_invalid"


def test_archived_project_rejects_new_document(client):
    token = login(client, "a@example.com")
    project_id = project(client, token)
    client.patch(f"/api/v1/projects/{project_id}", headers=h(token), json={"is_archived": True})
    response = client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=payload())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "planning_document_state_invalid"
