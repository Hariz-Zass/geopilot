from __future__ import annotations

import hashlib
import io
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db import get_db_session
from app.db.base import Base
from app.main import create_app


@pytest.fixture()
def session_factory(tmp_path, monkeypatch) -> Generator[sessionmaker[Session], None, None]:
    monkeypatch.setenv("DOCUMENT_STORAGE_ROOT", str(tmp_path / "documents"))
    get_settings.cache_clear()
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
    get_settings.cache_clear()


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


def make_pdf(text: str | None = "Density 30 units per hectare") -> bytes:
    if text is None:
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
    output = io.BytesIO()
    c = canvas.Canvas(output)
    c.drawString(72, 720, text)
    c.showPage()
    c.save()
    return output.getvalue()


def register_version(client: TestClient, token: str, pdf: bytes):
    project_id = client.post("/api/v1/projects", headers=h(token), json={"name": "P"}).json()["id"]
    checksum = hashlib.sha256(pdf).hexdigest()
    payload = {
        "title": "RT Example",
        "document_class": "RT",
        "authority": "PLANMalaysia Example",
        "initial_version": {
            "source_kind": "upload",
            "source_filename": "rt.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": len(pdf),
            "checksum_sha256": checksum,
        },
    }
    document = client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=payload).json()
    version = client.get(f"/api/v1/projects/{project_id}/documents/{document['id']}/versions", headers=h(token)).json()[0]
    return project_id, document["id"], version["id"]


def ingest(client, token, project_id, document_id, version_id, pdf, content_type="application/pdf"):
    return client.post(
        f"/api/v1/projects/{project_id}/documents/{document_id}/versions/{version_id}/ingest-pdf",
        headers=h(token),
        files={"file": ("rt.pdf", pdf, content_type)},
    )


def test_text_pdf_is_checksum_verified_stored_and_extracted(client):
    token = login(client, "a@example.com")
    pdf = make_pdf()
    project_id, document_id, version_id = register_version(client, token, pdf)
    response = ingest(client, token, project_id, document_id, version_id, pdf)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] == 1
    assert body["text_page_count"] == 1
    assert body["requires_ocr_page_count"] == 0
    assert body["extraction_state"] == "ready"
    assert body["version"]["ingestion_state"] == "available"
    assert body["version"]["storage_uri"].startswith("local://documents/")
    assert body["version"]["provenance"]["checksum_verified"] is True

    pages = client.get(
        f"/api/v1/projects/{project_id}/documents/{document_id}/versions/{version_id}/pages",
        headers=h(token),
    )
    assert pages.status_code == 200
    page = pages.json()[0]
    assert "Density 30 units per hectare" in page["extracted_text"]
    assert page["extraction_state"] == "ready"
    assert page["requires_ocr"] is False


def test_blank_pdf_requires_ocr_review(client):
    token = login(client, "a@example.com")
    pdf = make_pdf(None)
    project_id, document_id, version_id = register_version(client, token, pdf)
    response = ingest(client, token, project_id, document_id, version_id, pdf)
    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 1
    assert body["text_page_count"] == 0
    assert body["requires_ocr_page_count"] == 1
    assert body["extraction_state"] == "requires_review"
    assert body["review_state"] == "requires_review"


def test_checksum_mismatch_fails_closed_without_pages(client):
    token = login(client, "a@example.com")
    original = make_pdf("Original")
    changed = make_pdf("Changed")
    project_id, document_id, version_id = register_version(client, token, original)
    response = ingest(client, token, project_id, document_id, version_id, changed)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pdf_checksum_mismatch"
    pages = client.get(
        f"/api/v1/projects/{project_id}/documents/{document_id}/versions/{version_id}/pages", headers=h(token)
    )
    assert pages.json() == []


def test_non_pdf_signature_and_wrong_content_type_rejected(client):
    token = login(client, "a@example.com")
    fake = b"not a pdf at all"
    project_id, document_id, version_id = register_version(client, token, fake)
    response = ingest(client, token, project_id, document_id, version_id, fake)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_pdf"

    pdf = make_pdf()
    project_id2, document_id2, version_id2 = register_version(client, token, pdf)
    response = ingest(client, token, project_id2, document_id2, version_id2, pdf, "text/plain")
    assert response.status_code == 422


def test_reingestion_of_immutable_version_rejected(client):
    token = login(client, "a@example.com")
    pdf = make_pdf()
    project_id, document_id, version_id = register_version(client, token, pdf)
    assert ingest(client, token, project_id, document_id, version_id, pdf).status_code == 200
    response = ingest(client, token, project_id, document_id, version_id, pdf)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pdf_already_ingested"


def test_cross_owner_page_and_ingestion_access_fail_closed(client):
    a = login(client, "a@example.com")
    b = login(client, "b@example.com")
    pdf = make_pdf()
    project_id, document_id, version_id = register_version(client, a, pdf)
    assert ingest(client, b, project_id, document_id, version_id, pdf).status_code == 404
    assert client.get(
        f"/api/v1/projects/{project_id}/documents/{document_id}/versions/{version_id}/pages", headers=h(b)
    ).status_code == 404
