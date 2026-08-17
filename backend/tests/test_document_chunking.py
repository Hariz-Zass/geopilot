from __future__ import annotations

import hashlib
import io

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db import get_db_session
from app.db.base import Base
from app.main import create_app
from app.services.document_chunking import _page_windows


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENT_STORAGE_ROOT", str(tmp_path / "docs"))
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
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


def make_pdf(page_texts: list[str | None]) -> bytes:
    output = io.BytesIO()
    c = canvas.Canvas(output)
    for text in page_texts:
        if text:
            c.drawString(24, 720, text)
        c.showPage()
    c.save()
    return output.getvalue()


def register_and_ingest(client: TestClient, token: str, pdf: bytes):
    project_id = client.post("/api/v1/projects", headers=h(token), json={"name": "P"}).json()["id"]
    payload = {
        "title": "RT Example",
        "document_class": "RT",
        "authority": "PLANMalaysia Example",
        "initial_version": {
            "source_kind": "upload",
            "source_filename": "rt.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": len(pdf),
            "checksum_sha256": hashlib.sha256(pdf).hexdigest(),
        },
    }
    document = client.post(f"/api/v1/projects/{project_id}/documents", headers=h(token), json=payload).json()
    versions_url = f"/api/v1/projects/{project_id}/documents/{document['id']}/versions"
    version = client.get(versions_url, headers=h(token)).json()[0]
    response = client.post(
        f"{versions_url}/{version['id']}/ingest-pdf",
        headers=h(token),
        files={"file": ("rt.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return project_id, document["id"], version["id"]


def chunk_urls(project_id, document_id, version_id):
    base = f"/api/v1/projects/{project_id}/documents/{document_id}/versions/{version_id}/chunks"
    return f"{base}/build", base


def test_page_windows_are_deterministic_bounded_and_overlap():
    text = " ".join(f"word{i:03d}" for i in range(150))
    a = _page_windows(text, max_chars=256, overlap_chars=64)
    b = _page_windows(text, max_chars=256, overlap_chars=64)
    assert a == b
    assert len(a) > 1
    assert all(0 <= start < end <= len(text) for start, end, _ in a)
    assert all(end - start <= 256 for start, end, _ in a)
    assert a[1][0] <= a[0][1]
    assert all(text[start:end] == chunk for start, end, chunk in a)


def test_build_chunks_preserves_page_lineage_and_stable_ids(client):
    token = login(client, "a@example.com")
    long_text = "Density policy evidence " * 80
    pdf = make_pdf([long_text, "Second page evidence about open space."])
    project_id, document_id, version_id = register_and_ingest(client, token, pdf)
    build_url, list_url = chunk_urls(project_id, document_id, version_id)

    first = client.post(build_url, headers=h(token), json={"max_chars": 256, "overlap_chars": 64})
    assert first.status_code == 200, first.text
    summary = first.json()
    assert summary["chunk_count"] >= 2
    assert summary["chunked_page_count"] == 2
    assert summary["chunker_version"] == "page_chars_v1"
    assert summary["version"]["index_state"] == "pending"

    chunks = client.get(list_url, headers=h(token)).json()
    assert [c["chunk_sequence"] for c in chunks] == list(range(len(chunks)))
    assert {c["page_number"] for c in chunks} == {1, 2}
    assert all(c["text_sha256"] == hashlib.sha256(c["text"].encode()).hexdigest() for c in chunks)
    ids_before = [c["id"] for c in chunks]

    second = client.post(build_url, headers=h(token), json={"max_chars": 256, "overlap_chars": 64})
    assert second.status_code == 200
    ids_after = [c["id"] for c in client.get(list_url, headers=h(token)).json()]
    assert ids_after == ids_before


def test_page_filter_and_blank_pages_are_skipped(client):
    token = login(client, "a@example.com")
    pdf = make_pdf(["Evidence on page one " * 30, None])
    project_id, document_id, version_id = register_and_ingest(client, token, pdf)
    build_url, list_url = chunk_urls(project_id, document_id, version_id)
    response = client.post(build_url, headers=h(token), json={"max_chars": 256, "overlap_chars": 32})
    assert response.status_code == 200
    assert response.json()["chunked_page_count"] == 1
    assert response.json()["skipped_page_count"] == 1
    assert response.json()["version"]["review_state"] == "requires_review"
    assert client.get(f"{list_url}?page_number=1", headers=h(token)).status_code == 200
    assert client.get(f"{list_url}?page_number=2", headers=h(token)).json() == []


def test_no_chunkable_text_fails_closed(client):
    token = login(client, "a@example.com")
    pdf = make_pdf([None])
    project_id, document_id, version_id = register_and_ingest(client, token, pdf)
    build_url, _ = chunk_urls(project_id, document_id, version_id)
    response = client.post(build_url, headers=h(token), json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_chunking_state_invalid"


def test_chunk_config_validation_fails_before_processing(client):
    token = login(client, "a@example.com")
    pdf = make_pdf(["Evidence " * 100])
    project_id, document_id, version_id = register_and_ingest(client, token, pdf)
    build_url, _ = chunk_urls(project_id, document_id, version_id)
    response = client.post(build_url, headers=h(token), json={"max_chars": 256, "overlap_chars": 200})
    assert response.status_code == 422


def test_cross_owner_chunk_access_fails_closed(client):
    a = login(client, "a@example.com")
    b = login(client, "b@example.com")
    pdf = make_pdf(["Evidence " * 100])
    project_id, document_id, version_id = register_and_ingest(client, a, pdf)
    build_url, list_url = chunk_urls(project_id, document_id, version_id)
    assert client.post(build_url, headers=h(b), json={}).status_code == 404
    assert client.get(list_url, headers=h(b)).status_code == 404
