from __future__ import annotations

import hashlib
import io

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db_session
from app.db.base import Base
from app.main import create_app
from app.models.planning_document import DocumentChunkEmbedding, DocumentEmbeddingIndex, DocumentVersion
from app.services.embedding_providers import EmbeddingBatch, EmbeddingProviderError


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


def login(client, email="a@example.com"):
    client.post("/api/v1/auth/register", json={"email": email, "password": "correct horse battery staple", "display_name": "A"})
    return client.post("/api/v1/auth/login", json={"email": email, "password": "correct horse battery staple"}).json()["access_token"]


def h(token): return {"Authorization": f"Bearer {token}"}


def make_pdf(text="Density evidence " * 100):
    out=io.BytesIO(); c=canvas.Canvas(out); c.drawString(24,720,text); c.showPage(); c.save(); return out.getvalue()


def prepare(client, token):
    pdf=make_pdf(); pid=client.post("/api/v1/projects",headers=h(token),json={"name":"P"}).json()["id"]
    doc=client.post(f"/api/v1/projects/{pid}/documents",headers=h(token),json={"title":"RT","document_class":"RT","authority":"A","initial_version":{"source_kind":"upload","source_filename":"a.pdf","file_size_bytes":len(pdf),"checksum_sha256":hashlib.sha256(pdf).hexdigest()}}).json()
    versions=f"/api/v1/projects/{pid}/documents/{doc['id']}/versions"; vid=client.get(versions,headers=h(token)).json()[0]["id"]
    assert client.post(f"{versions}/{vid}/ingest-pdf",headers=h(token),files={"file":("a.pdf",pdf,"application/pdf")}).status_code==200
    assert client.post(f"{versions}/{vid}/chunks/build",headers=h(token),json={"max_chars":256,"overlap_chars":32}).status_code==200
    return pid,doc["id"],vid


def test_index_build_persists_exact_provider_model_dimensions_and_sets_ready(client, monkeypatch, session_factory):
    token=login(client); pid,did,vid=prepare(client,token)
    def fake(texts, settings=None):
        return EmbeddingBatch("ollama","test-embed","rev-a",[[float(i),0.5,1.0] for i,_ in enumerate(texts)])
    monkeypatch.setattr("app.services.document_indexing.embed_with_fallback",fake)
    url=f"/api/v1/projects/{pid}/documents/{did}/versions/{vid}/chunks/index"
    r=client.post(url,headers=h(token),json={}); assert r.status_code==200,r.text
    body=r.json(); assert body["version"]["index_state"]=="ready"; assert body["index"]["provider"]=="ollama"; assert body["index"]["dimensions"]==3; assert body["index"]["chunk_count"]>0
    with session_factory() as s:
        rows=list(s.scalars(select(DocumentChunkEmbedding))); assert len(rows)==body["index"]["chunk_count"]; assert all(x.dimensions==3 and len(x.embedding)==3 for x in rows)


def test_same_index_is_idempotent_without_force(client, monkeypatch):
    token=login(client); pid,did,vid=prepare(client,token); calls={"n":0}
    def fake(texts, settings=None):
        calls["n"]+=1; return EmbeddingBatch("ollama","m","r",[[0.1,0.2] for _ in texts])
    monkeypatch.setattr("app.services.document_indexing.embed_with_fallback",fake)
    url=f"/api/v1/projects/{pid}/documents/{did}/versions/{vid}/chunks/index"
    a=client.post(url,headers=h(token),json={}).json(); b=client.post(url,headers=h(token),json={}).json()
    assert a["index"]["id"]==b["index"]["id"]


def test_provider_failure_marks_version_failed(client, monkeypatch, session_factory):
    token=login(client); pid,did,vid=prepare(client,token)
    def fail(texts, settings=None): raise EmbeddingProviderError("offline")
    monkeypatch.setattr("app.services.document_indexing.embed_with_fallback",fail)
    url=f"/api/v1/projects/{pid}/documents/{did}/versions/{vid}/chunks/index"
    r=client.post(url,headers=h(token),json={}); assert r.status_code==503; assert r.json()["error"]["code"]=="embedding_provider_failed"
    with session_factory() as s: assert s.get(DocumentVersion, __import__('uuid').UUID(vid)).index_state=="failed"


def test_inconsistent_dimensions_fail_closed(client, monkeypatch):
    token=login(client); pid,did,vid=prepare(client,token)
    def bad(texts, settings=None): return EmbeddingBatch("ollama","m","r",[[0.1,0.2] if i==0 else [0.1] for i,_ in enumerate(texts)])
    monkeypatch.setattr("app.services.document_indexing.embed_with_fallback",bad)
    r=client.post(f"/api/v1/projects/{pid}/documents/{did}/versions/{vid}/chunks/index",headers=h(token),json={})
    assert r.status_code==503


def test_cross_owner_index_access_fails_closed(client, monkeypatch):
    a=login(client,"a@example.com"); b=login(client,"b@example.com"); pid,did,vid=prepare(client,a)
    monkeypatch.setattr("app.services.document_indexing.embed_with_fallback", lambda texts,settings=None: EmbeddingBatch("ollama","m","r",[[0.1,0.2] for _ in texts]))
    url=f"/api/v1/projects/{pid}/documents/{did}/versions/{vid}/chunks/index"
    assert client.post(url,headers=h(b),json={}).status_code==404


def test_list_embedding_indexes(client, monkeypatch):
    token=login(client); pid,did,vid=prepare(client,token)
    monkeypatch.setattr("app.services.document_indexing.embed_with_fallback", lambda texts,settings=None: EmbeddingBatch("openai","embed-model","provider_managed",[[0.1,0.2] for _ in texts]))
    base=f"/api/v1/projects/{pid}/documents/{did}/versions/{vid}"
    assert client.post(base+"/chunks/index",headers=h(token),json={}).status_code==200
    rows=client.get(base+"/embedding-indexes",headers=h(token)).json(); assert len(rows)==1; assert rows[0]["provider"]=="openai"


def test_ready_index_is_not_reused_when_chunk_lineage_changes(client, monkeypatch, session_factory):
    token=login(client); pid,did,vid=prepare(client,token)
    monkeypatch.setattr("app.services.document_indexing.embed_with_fallback", lambda texts,settings=None: EmbeddingBatch("ollama","m","r",[[0.1,0.2] for _ in texts]))
    base=f"/api/v1/projects/{pid}/documents/{did}/versions/{vid}"
    first=client.post(base+"/chunks/index",headers=h(token),json={}); assert first.status_code==200
    with session_factory() as s:
        row=s.scalar(select(DocumentChunkEmbedding))
        row.text_sha256="0"*64
        s.commit()
    second=client.post(base+"/chunks/index",headers=h(token),json={}); assert second.status_code==200
    with session_factory() as s:
        hashes=list(s.scalars(select(DocumentChunkEmbedding.text_sha256)))
        assert hashes and all(item != "0"*64 for item in hashes)
