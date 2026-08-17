from __future__ import annotations

import hashlib
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db_session
from app.db.base import Base
from app.main import create_app
from app.models.planning_document import DocumentChunk


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


def login(client, email="policy@example.com"):
    password="correct horse battery staple"
    client.post("/api/v1/auth/register", json={"email":email,"password":password,"display_name":"Policy Reviewer"})
    return client.post("/api/v1/auth/login", json={"email":email,"password":password}).json()["access_token"]


def make_pdf(text):
    out=io.BytesIO(); c=canvas.Canvas(out); c.drawString(24,720,text); c.showPage(); c.save(); return out.getvalue()


def prepared_citation(client, token):
    pid=client.post("/api/v1/projects",headers=h(token),json={"name":"Policy Project"}).json()["id"]
    pdf=make_pdf("Residential density is stated as 60 units per hectare in this controlled test source.")
    doc=client.post(f"/api/v1/projects/{pid}/documents",headers=h(token),json={
        "title":"RT Policy Test","document_class":"RT","authority":"PLAN Test",
        "initial_version":{"source_kind":"upload","source_filename":"rt.pdf","file_size_bytes":len(pdf),"checksum_sha256":hashlib.sha256(pdf).hexdigest(),"publication_year":2035}
    }).json()
    versions=client.get(f"/api/v1/projects/{pid}/documents/{doc['id']}/versions",headers=h(token)).json(); vid=versions[0]["id"]
    base=f"/api/v1/projects/{pid}/documents/{doc['id']}/versions/{vid}"
    assert client.post(f"{base}/ingest-pdf",headers=h(token),files={"file":("rt.pdf",pdf,"application/pdf")}).status_code==200
    assert client.post(f"{base}/chunks/build",headers=h(token),json={"max_chars":256,"overlap_chars":32}).status_code==200
    hit=client.post(f"/api/v1/projects/{pid}/document-search",headers=h(token),json={"query":"density 60 units hectare"}).json()["hits"][0]
    return pid, doc["id"], vid, hit


def create_candidate(client, token, pid, citation):
    return client.post(f"/api/v1/projects/{pid}/policy-references",headers=h(token),json={
        "citation":citation,
        "label":"Residential density passage",
        "policy_statement":"The cited source mentions a residential density value of 60 units per hectare.",
        "applicability_notes":"Applicability to the active site is not yet assessed."
    })


def test_candidate_is_grounded_in_validated_citation_and_not_auto_verified(client):
    token=login(client); pid,_did,_vid,hit=prepared_citation(client,token)
    r=create_candidate(client,token,pid,hit["citation"])
    assert r.status_code==201,r.text
    item=r.json()
    assert item["source_wording"]==hit["text"]
    assert item["document_chunk_id"]==hit["citation"]["document_chunk_id"]
    assert item["representation_state"]=="draft"
    assert item["review_state"]=="unreviewed"
    assert item["applicability_status"]=="unassessed"


def test_candidate_creation_rejects_tampered_source_reference(client):
    token=login(client); pid,_did,_vid,hit=prepared_citation(client,token)
    ref=dict(hit["citation"]); ref["chunk_text_sha256"]="0"*64
    r=create_candidate(client,token,pid,ref)
    assert r.status_code==409
    assert r.json()["error"]["code"]=="policy_reference_source_stale"


def test_cross_project_citation_cannot_create_policy_reference(client):
    token=login(client); pid,_did,_vid,hit=prepared_citation(client,token)
    other=client.post("/api/v1/projects",headers=h(token),json={"name":"Other"}).json()["id"]
    r=create_candidate(client,token,other,hit["citation"])
    assert r.status_code in {404,409}


def test_explicit_review_verifies_and_finalizes_candidate(client):
    token=login(client); pid,_did,_vid,hit=prepared_citation(client,token)
    candidate=create_candidate(client,token,pid,hit["citation"]).json()
    r=client.post(f"/api/v1/projects/{pid}/policy-references/{candidate['id']}/review",headers=h(token),json={
        "action":"verify","applicability_status":"unassessed","review_notes":"Source interpretation checked against cited passage."
    })
    assert r.status_code==200,r.text
    item=r.json()
    assert item["representation_state"]=="final"
    assert item["review_state"]=="verified"
    assert item["reviewed_by_user_id"] is not None
    assert item["reviewed_at"] is not None


def test_unverified_candidate_cannot_be_resolved_for_policy_use(client):
    token=login(client); pid,_did,_vid,hit=prepared_citation(client,token)
    item=create_candidate(client,token,pid,hit["citation"]).json()
    r=client.post(f"/api/v1/projects/{pid}/policy-references/{item['id']}/resolve",headers=h(token))
    assert r.status_code==409
    assert r.json()["error"]["code"]=="policy_reference_state_invalid"


def test_verified_reference_resolves_with_applicability_and_statutory_limitations(client):
    token=login(client); pid,_did,_vid,hit=prepared_citation(client,token)
    item=create_candidate(client,token,pid,hit["citation"]).json()
    client.post(f"/api/v1/projects/{pid}/policy-references/{item['id']}/review",headers=h(token),json={"action":"verify"})
    r=client.post(f"/api/v1/projects/{pid}/policy-references/{item['id']}/resolve",headers=h(token))
    assert r.status_code==200,r.text
    body=r.json()
    assert body["status"]=="validated"
    assert body["source_citation"]["text"]==hit["text"]
    joined=" ".join(body["limitations"]).lower()
    assert "applicability" in joined
    assert "statutory" in joined


def test_verified_reference_source_tampering_fails_closed(client,session_factory):
    token=login(client); pid,_did,_vid,hit=prepared_citation(client,token)
    item=create_candidate(client,token,pid,hit["citation"]).json()
    client.post(f"/api/v1/projects/{pid}/policy-references/{item['id']}/review",headers=h(token),json={"action":"verify"})
    with session_factory() as s:
        chunk=s.get(DocumentChunk,uuid.UUID(hit["citation"]["document_chunk_id"])); chunk.text="tampered"; s.commit()
    r=client.post(f"/api/v1/projects/{pid}/policy-references/{item['id']}/resolve",headers=h(token))
    assert r.status_code==409
    assert r.json()["error"]["code"] in {"policy_reference_source_stale","policy_reference_source_unavailable"}


def test_final_policy_content_is_immutable_but_can_be_archived(client):
    token=login(client); pid,_did,_vid,hit=prepared_citation(client,token)
    item=create_candidate(client,token,pid,hit["citation"]).json()
    item=client.post(f"/api/v1/projects/{pid}/policy-references/{item['id']}/review",headers=h(token),json={"action":"verify"}).json()
    r=client.patch(f"/api/v1/projects/{pid}/policy-references/{item['id']}",headers=h(token),json={"policy_statement":"changed after final"})
    assert r.status_code==409
    r=client.patch(f"/api/v1/projects/{pid}/policy-references/{item['id']}",headers=h(token),json={"is_archived":True})
    assert r.status_code==200 and r.json()["is_archived"] is True
    use=client.post(f"/api/v1/projects/{pid}/policy-references/{item['id']}/resolve",headers=h(token))
    assert use.status_code==409


def test_requires_review_does_not_promote_policy_truth(client):
    token=login(client); pid,_did,_vid,hit=prepared_citation(client,token)
    item=create_candidate(client,token,pid,hit["citation"]).json()
    r=client.post(f"/api/v1/projects/{pid}/policy-references/{item['id']}/review",headers=h(token),json={
        "action":"requires_review","applicability_status":"requires_review","review_notes":"Authority scope unclear."
    })
    assert r.status_code==200
    assert r.json()["representation_state"]=="draft"
    assert r.json()["review_state"]=="requires_review"


def test_rejected_candidate_is_final_but_never_resolvable_for_use(client):
    token=login(client); pid,_did,_vid,hit=prepared_citation(client,token)
    item=create_candidate(client,token,pid,hit["citation"]).json()
    r=client.post(f"/api/v1/projects/{pid}/policy-references/{item['id']}/review",headers=h(token),json={"action":"reject","review_notes":"Interpretation overstates source wording."})
    assert r.status_code==200
    assert r.json()["representation_state"]=="final" and r.json()["review_state"]=="rejected"
    use=client.post(f"/api/v1/projects/{pid}/policy-references/{item['id']}/resolve",headers=h(token))
    assert use.status_code==409


def test_cross_owner_policy_reference_is_missing_equivalent(client):
    a=login(client,"a@example.com"); pid,_did,_vid,hit=prepared_citation(client,a)
    item=create_candidate(client,a,pid,hit["citation"]).json()
    b=login(client,"b@example.com")
    r=client.get(f"/api/v1/projects/{pid}/policy-references/{item['id']}",headers=h(b))
    assert r.status_code==404
