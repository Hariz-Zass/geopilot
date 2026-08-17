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
from app.models.planning_document import DocumentChunk, DocumentChunkEmbedding, DocumentEmbeddingIndex, DocumentVersion, PlanningDocument
from app.services.embedding_providers import EmbeddingBatch, EmbeddingProviderError


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENT_STORAGE_ROOT", str(tmp_path / "docs"))
    engine=create_engine("sqlite+pysqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine,expire_on_commit=False)


@pytest.fixture()
def client(session_factory):
    app=create_app()
    def override():
        with session_factory() as session: yield session
    app.dependency_overrides[get_db_session]=override
    with TestClient(app) as c: yield c


def login(client,email="a@example.com"):
    client.post("/api/v1/auth/register",json={"email":email,"password":"correct horse battery staple","display_name":"A"})
    return client.post("/api/v1/auth/login",json={"email":email,"password":"correct horse battery staple"}).json()["access_token"]


def h(token): return {"Authorization":f"Bearer {token}"}


def make_pdf(text):
    out=io.BytesIO(); c=canvas.Canvas(out); c.drawString(24,720,text); c.showPage(); c.save(); return out.getvalue()


def add_doc(client,token,pid,title,text,doc_class="RT"):
    pdf=make_pdf(text)
    doc=client.post(f"/api/v1/projects/{pid}/documents",headers=h(token),json={"title":title,"document_class":doc_class,"authority":"PLAN Test","initial_version":{"source_kind":"upload","source_filename":title+".pdf","file_size_bytes":len(pdf),"checksum_sha256":hashlib.sha256(pdf).hexdigest(),"publication_year":2035}}).json()
    base=f"/api/v1/projects/{pid}/documents/{doc['id']}/versions"
    vid=client.get(base,headers=h(token)).json()[0]["id"]
    assert client.post(f"{base}/{vid}/ingest-pdf",headers=h(token),files={"file":("x.pdf",pdf,"application/pdf")}).status_code==200
    assert client.post(f"{base}/{vid}/chunks/build",headers=h(token),json={"max_chars":256,"overlap_chars":32}).status_code==200
    return doc["id"],vid


def seed_embeddings(session_factory,vid,query_vector=(1.0,0.0),chunk_vectors=None):
    with session_factory() as s:
        version=s.get(DocumentVersion,uuid.UUID(vid)); chunks=list(s.scalars(select(DocumentChunk).where(DocumentChunk.document_version_id==version.id).order_by(DocumentChunk.chunk_sequence)))
        idx=DocumentEmbeddingIndex(id=uuid.uuid4(),document_version_id=version.id,provider="ollama",model_name="test-embed",model_revision="server_resolved",dimensions=2,state="ready",chunk_count=len(chunks))
        s.add(idx); s.flush()
        vectors=chunk_vectors or [[1.0,0.0] for _ in chunks]
        for chunk,vector in zip(chunks,vectors,strict=True):
            s.add(DocumentChunkEmbedding(id=uuid.uuid4(),embedding_index_id=idx.id,document_chunk_id=chunk.id,text_sha256=chunk.text_sha256,dimensions=2,embedding=vector))
        version.index_state="ready"; s.commit()
    return list(query_vector)


class FakeProvider:
    provider_name="ollama"; model_name="test-embed"; model_revision="server_resolved"
    def __init__(self,vector=(1.0,0.0)): self.vector=list(vector)
    def embed(self,texts): return EmbeddingBatch("ollama","test-embed","server_resolved",[self.vector for _ in texts])


def test_keyword_only_returns_exact_provenance(client):
    token=login(client); pid=client.post("/api/v1/projects",headers=h(token),json={"name":"P"}).json()["id"]
    did,vid=add_doc(client,token,pid,"RT Density","The residential density value is 60 units per hectare.")
    r=client.post(f"/api/v1/projects/{pid}/document-search",headers=h(token),json={"query":"density 60 units hectare"})
    assert r.status_code==200,r.text; body=r.json(); assert body["status"]=="degraded"; assert body["search_mode"]=="keyword_only"; assert body["hits"]
    p=body["hits"][0]["provenance"]; assert p["document_id"]==did and p["document_version_id"]==vid and p["page_number"]==1 and len(p["chunk_text_sha256"])==64


def test_hybrid_rrf_combines_keyword_and_vector(client,session_factory,monkeypatch):
    token=login(client); pid=client.post("/api/v1/projects",headers=h(token),json={"name":"P"}).json()["id"]
    _did,vid=add_doc(client,token,pid,"RT","Density standard 60 units per hectare. Mixed residential planning evidence.")
    seed_embeddings(session_factory,vid)
    monkeypatch.setattr("app.services.document_retrieval.build_provider",lambda name:FakeProvider())
    r=client.post(f"/api/v1/projects/{pid}/document-search",headers=h(token),json={"query":"density residential","top_k":5})
    body=r.json(); assert r.status_code==200,r.text; assert body["status"]=="evaluated"; assert body["search_mode"]=="hybrid"; assert body["hits"][0]["keyword_rank"]==1; assert body["hits"][0]["vector_rank"]==1; assert body["hits"][0]["fused_score"]>0


def test_vector_provider_failure_degrades_to_keyword(client,session_factory,monkeypatch):
    token=login(client); pid=client.post("/api/v1/projects",headers=h(token),json={"name":"P"}).json()["id"]
    _did,vid=add_doc(client,token,pid,"RT","Open space density planning evidence."); seed_embeddings(session_factory,vid)
    monkeypatch.setattr("app.services.document_retrieval.build_provider",lambda name: (_ for _ in ()).throw(EmbeddingProviderError("offline")))
    r=client.post(f"/api/v1/projects/{pid}/document-search",headers=h(token),json={"query":"density"}); body=r.json()
    assert r.status_code==200; assert body["status"]=="degraded"; assert body["search_mode"]=="keyword_only"; assert any("Vector retrieval unavailable" in x for x in body["limitations"])


def test_no_match_returns_insufficient_evidence(client):
    token=login(client); pid=client.post("/api/v1/projects",headers=h(token),json={"name":"P"}).json()["id"]
    add_doc(client,token,pid,"RT","Only drainage information appears here.")
    r=client.post(f"/api/v1/projects/{pid}/document-search",headers=h(token),json={"query":"quantum banana density"}); body=r.json()
    assert r.status_code==200; assert body["status"]=="insufficient_evidence"; assert body["result_count"]==0


def test_cross_owner_search_fails_closed(client):
    a=login(client,"a@example.com"); b=login(client,"b@example.com")
    pid=client.post("/api/v1/projects",headers=h(a),json={"name":"P"}).json()["id"]; add_doc(client,a,pid,"RT","Density 60 units per hectare")
    r=client.post(f"/api/v1/projects/{pid}/document-search",headers=h(b),json={"query":"density"}); assert r.status_code==404


def test_document_filter_prevents_cross_document_result(client):
    token=login(client); pid=client.post("/api/v1/projects",headers=h(token),json={"name":"P"}).json()["id"]
    d1,_=add_doc(client,token,pid,"RT A","Density 60 units per hectare")
    add_doc(client,token,pid,"RT B","Density 90 units per hectare")
    body=client.post(f"/api/v1/projects/{pid}/document-search",headers=h(token),json={"query":"density","document_ids":[d1]}).json()
    assert body["hits"] and {hit["provenance"]["document_id"] for hit in body["hits"]}=={d1}


def test_archived_document_is_excluded(client):
    token=login(client); pid=client.post("/api/v1/projects",headers=h(token),json={"name":"P"}).json()["id"]
    did,_=add_doc(client,token,pid,"RT","Density 60 units per hectare")
    assert client.patch(f"/api/v1/projects/{pid}/documents/{did}",headers=h(token),json={"is_archived":True}).status_code==200
    body=client.post(f"/api/v1/projects/{pid}/document-search",headers=h(token),json={"query":"density"}).json(); assert body["result_count"]==0


def test_invalid_duplicate_filter_ids_rejected(client):
    token=login(client); pid=client.post("/api/v1/projects",headers=h(token),json={"name":"P"}).json()["id"]; x=str(uuid.uuid4())
    r=client.post(f"/api/v1/projects/{pid}/document-search",headers=h(token),json={"query":"density","document_ids":[x,x]}); assert r.status_code==422

def test_stale_index_state_is_not_used_for_vector_retrieval(client,session_factory,monkeypatch):
    token=login(client); pid=client.post("/api/v1/projects",headers=h(token),json={"name":"P"}).json()["id"]
    _did,vid=add_doc(client,token,pid,"RT","Density 60 units per hectare")
    seed_embeddings(session_factory,vid)
    with session_factory() as s:
        version=s.get(DocumentVersion,uuid.UUID(vid)); version.index_state="pending"; s.commit()
    monkeypatch.setattr("app.services.document_retrieval.build_provider",lambda name:FakeProvider())
    body=client.post(f"/api/v1/projects/{pid}/document-search",headers=h(token),json={"query":"density"}).json()
    assert body["search_mode"]=="keyword_only"
    assert any("no ready embedding index" in item.lower() for item in body["limitations"])


def test_embedding_hash_mismatch_is_excluded_from_vector_arm(client,session_factory,monkeypatch):
    token=login(client); pid=client.post("/api/v1/projects",headers=h(token),json={"name":"P"}).json()["id"]
    _did,vid=add_doc(client,token,pid,"RT","Density 60 units per hectare")
    seed_embeddings(session_factory,vid)
    with session_factory() as s:
        emb=s.scalar(select(DocumentChunkEmbedding)); emb.text_sha256="0"*64; s.commit()
    monkeypatch.setattr("app.services.document_retrieval.build_provider",lambda name:FakeProvider())
    body=client.post(f"/api/v1/projects/{pid}/document-search",headers=h(token),json={"query":"density"}).json()
    assert body["search_mode"]=="keyword_only"
