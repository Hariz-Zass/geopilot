from __future__ import annotations

import hashlib
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db_session
from app.db.base import Base
from app.main import create_app
from app.models.planning_document import DocumentChunk, DocumentPage, DocumentVersion, PlanningDocument


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENT_STORAGE_ROOT", str(tmp_path / "docs"))
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def client(session_factory):
    app = create_app()
    def override():
        with session_factory() as session:
            yield session
    app.dependency_overrides[get_db_session] = override
    with TestClient(app) as c:
        yield c


def h(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email="cite@example.com"):
    client.post("/api/v1/auth/register", json={"email": email, "password": "correct horse battery staple", "display_name": "C"})
    return client.post("/api/v1/auth/login", json={"email": email, "password": "correct horse battery staple"}).json()["access_token"]


def make_pdf(text):
    out = io.BytesIO(); c = canvas.Canvas(out); c.drawString(24, 720, text); c.showPage(); c.save(); return out.getvalue()


def prepared(client, token):
    pid = client.post("/api/v1/projects", headers=h(token), json={"name": "Citation P"}).json()["id"]
    pdf = make_pdf("Residential density value is 60 units per hectare under the test plan.")
    doc = client.post(f"/api/v1/projects/{pid}/documents", headers=h(token), json={
        "title":"RT Citation Test", "document_class":"RT", "authority":"PLAN Test",
        "initial_version":{"source_kind":"upload","source_filename":"rt.pdf","file_size_bytes":len(pdf),"checksum_sha256":hashlib.sha256(pdf).hexdigest(),"publication_year":2035}
    }).json()
    versions = client.get(f"/api/v1/projects/{pid}/documents/{doc['id']}/versions", headers=h(token)).json()
    vid = versions[0]["id"]
    base=f"/api/v1/projects/{pid}/documents/{doc['id']}/versions/{vid}"
    assert client.post(f"{base}/ingest-pdf", headers=h(token), files={"file":("rt.pdf",pdf,"application/pdf")}).status_code==200
    assert client.post(f"{base}/chunks/build", headers=h(token), json={"max_chars":256,"overlap_chars":32}).status_code==200
    hit = client.post(f"/api/v1/projects/{pid}/document-search", headers=h(token), json={"query":"density 60 units hectare"}).json()["hits"][0]
    return pid, doc["id"], vid, hit


def test_search_hit_carries_citation_reference_and_label(client):
    token=login(client); pid,_did,_vid,hit=prepared(client,token)
    ref=hit["citation"]
    assert ref["version"]=="document_citation.v1"
    assert ref["project_id"]==pid
    assert ref["document_chunk_id"]==hit["provenance"]["document_chunk_id"]
    assert ref["version_checksum_sha256"]==hit["provenance"]["checksum_sha256"]
    assert ref["chunk_text_sha256"]==hit["provenance"]["chunk_text_sha256"]
    assert hit["citation_label"]=="RT Citation Test, p. 1"


def test_resolve_citation_returns_server_owned_text_and_metadata(client):
    token=login(client); pid,_did,_vid,hit=prepared(client,token)
    r=client.post(f"/api/v1/projects/{pid}/citations/resolve", headers=h(token), json={"references":[hit["citation"]]})
    assert r.status_code==200,r.text
    item=r.json()["citations"][0]
    assert item["status"]=="validated"
    assert item["text"]==hit["text"]
    assert item["page_number"]==1
    assert item["document_class"]=="RT"
    assert item["authority"]=="PLAN Test"
    assert any("applicability" in x.lower() for x in item["limitations"])


def test_tampered_hash_is_rejected_stale(client):
    token=login(client); pid,_did,_vid,hit=prepared(client,token)
    ref=dict(hit["citation"]); ref["chunk_text_sha256"]="0"*64
    r=client.post(f"/api/v1/projects/{pid}/citations/resolve", headers=h(token), json={"references":[ref]})
    assert r.status_code==409 and r.json()["error"]["code"]=="citation_reference_stale"


def test_tampered_page_number_is_rejected_stale(client):
    token=login(client); pid,_did,_vid,hit=prepared(client,token)
    ref=dict(hit["citation"]); ref["page_number"]=2
    r=client.post(f"/api/v1/projects/{pid}/citations/resolve", headers=h(token), json={"references":[ref]})
    assert r.status_code==409 and r.json()["error"]["code"]=="citation_reference_stale"


def test_cross_project_reference_replay_fails_closed(client):
    token=login(client); p1,_did,_vid,hit=prepared(client,token)
    p2=client.post("/api/v1/projects",headers=h(token),json={"name":"Other"}).json()["id"]
    r=client.post(f"/api/v1/projects/{p2}/citations/resolve",headers=h(token),json={"references":[hit["citation"]]})
    assert r.status_code==404


def test_cross_owner_reference_replay_fails_closed(client):
    a=login(client,"owner@example.com"); pid,_did,_vid,hit=prepared(client,a)
    b=login(client,"other@example.com")
    r=client.post(f"/api/v1/projects/{pid}/citations/resolve",headers=h(b),json={"references":[hit["citation"]]})
    assert r.status_code==404


def test_archived_document_citation_is_unavailable(client):
    token=login(client); pid,did,_vid,hit=prepared(client,token)
    assert client.patch(f"/api/v1/projects/{pid}/documents/{did}",headers=h(token),json={"is_archived":True}).status_code==200
    r=client.post(f"/api/v1/projects/{pid}/citations/resolve",headers=h(token),json={"references":[hit["citation"]]})
    assert r.status_code==409 and r.json()["error"]["code"]=="citation_source_unavailable"


def test_duplicate_chunk_references_are_rejected(client):
    token=login(client); pid,_did,_vid,hit=prepared(client,token)
    r=client.post(f"/api/v1/projects/{pid}/citations/resolve",headers=h(token),json={"references":[hit["citation"],hit["citation"]]})
    assert r.status_code==409


def test_persisted_source_mutation_is_detected(client,session_factory):
    token=login(client); pid,_did,_vid,hit=prepared(client,token)
    with session_factory() as s:
        chunk=s.get(DocumentChunk,uuid.UUID(hit["citation"]["document_chunk_id"])); chunk.text="mutated without changing hash"; s.commit()
    r=client.post(f"/api/v1/projects/{pid}/citations/resolve",headers=h(token),json={"references":[hit["citation"]]})
    assert r.status_code==409 and r.json()["error"]["code"]=="citation_reference_stale"


def test_page_hash_tampering_is_detected(client,session_factory):
    token=login(client); pid,_did,_vid,hit=prepared(client,token)
    with session_factory() as s:
        page=s.get(DocumentPage,uuid.UUID(hit["citation"]["document_page_id"])); page.text_sha256="1"*64; s.commit()
    r=client.post(f"/api/v1/projects/{pid}/citations/resolve",headers=h(token),json={"references":[hit["citation"]]})
    assert r.status_code==409


def test_chunk_text_and_hash_coordinated_tampering_still_fails_page_range_check(client,session_factory):
    token=login(client); pid,_did,_vid,hit=prepared(client,token)
    with session_factory() as s:
        chunk=s.get(DocumentChunk,uuid.UUID(hit["citation"]["document_chunk_id"]))
        chunk.text="coordinated tampered text"
        chunk.text_sha256=hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
        s.commit()
    ref=dict(hit["citation"]); ref["chunk_text_sha256"]=hashlib.sha256(b"coordinated tampered text").hexdigest()
    r=client.post(f"/api/v1/projects/{pid}/citations/resolve",headers=h(token),json={"references":[ref]})
    assert r.status_code==409 and r.json()["error"]["code"]=="citation_reference_stale"

def test_page_text_mutation_without_hash_update_is_detected(client,session_factory):
    token=login(client); pid,_did,_vid,hit=prepared(client,token)
    with session_factory() as s:
        page=s.get(DocumentPage,uuid.UUID(hit["citation"]["document_page_id"]))
        page.extracted_text=page.extracted_text+" tampered"
        s.commit()
    r=client.post(f"/api/v1/projects/{pid}/citations/resolve",headers=h(token),json={"references":[hit["citation"]]})
    assert r.status_code==409 and r.json()["error"]["code"]=="citation_reference_stale"
