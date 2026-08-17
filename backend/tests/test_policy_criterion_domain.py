from __future__ import annotations

import hashlib
import io

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db_session
from app.db.base import Base
from app.main import create_app


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


def login(client, email="criterion@example.com"):
    password = "correct horse battery staple"
    client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": "Criterion Reviewer"})
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]


def make_pdf(text):
    out = io.BytesIO()
    c = canvas.Canvas(out)
    c.drawString(24, 720, text)
    c.showPage()
    c.save()
    return out.getvalue()


def verified_policy_reference(client, token):
    pid = client.post("/api/v1/projects", headers=h(token), json={"name": "Criterion Project"}).json()["id"]
    text = "Residential density is stated as 60 units per hectare in this controlled test source."
    pdf = make_pdf(text)
    doc = client.post(
        f"/api/v1/projects/{pid}/documents",
        headers=h(token),
        json={
            "title": "RT Criterion Test",
            "document_class": "RT",
            "authority": "PLAN Test",
            "initial_version": {
                "source_kind": "upload",
                "source_filename": "rt.pdf",
                "file_size_bytes": len(pdf),
                "checksum_sha256": hashlib.sha256(pdf).hexdigest(),
                "publication_year": 2035,
            },
        },
    ).json()
    versions = client.get(f"/api/v1/projects/{pid}/documents/{doc['id']}/versions", headers=h(token)).json()
    vid = versions[0]["id"]
    base = f"/api/v1/projects/{pid}/documents/{doc['id']}/versions/{vid}"
    assert client.post(f"{base}/ingest-pdf", headers=h(token), files={"file": ("rt.pdf", pdf, "application/pdf")}).status_code == 200
    assert client.post(f"{base}/chunks/build", headers=h(token), json={"max_chars": 256, "overlap_chars": 32}).status_code == 200
    hit = client.post(f"/api/v1/projects/{pid}/document-search", headers=h(token), json={"query": "density 60 units hectare"}).json()["hits"][0]
    ref = client.post(
        f"/api/v1/projects/{pid}/policy-references",
        headers=h(token),
        json={
            "citation": hit["citation"],
            "label": "Density passage",
            "policy_statement": "The cited source mentions a residential density value of 60 units per hectare.",
        },
    ).json()
    ref = client.post(
        f"/api/v1/projects/{pid}/policy-references/{ref['id']}/review",
        headers=h(token),
        json={"action": "verify", "review_notes": "Verified against source."},
    ).json()
    return pid, ref, hit["text"]


def create_numeric(client, token, pid, ref_id, evidence, threshold="60", code="density.max"):
    return client.post(
        f"/api/v1/projects/{pid}/policy-criteria",
        headers=h(token),
        json={
            "policy_reference_id": ref_id,
            "code": code,
            "label": "Residential density criterion",
            "metric_key": "residential_density_units_per_hectare",
            "value_type": "numeric",
            "operator": "lte",
            "unit": "units_per_hectare",
            "threshold_numeric": threshold,
            "source_evidence_text": evidence,
            "interpretation_notes": "Reviewed deterministic representation of the cited numeric value.",
        },
    )


def test_verified_policy_reference_can_create_grounded_numeric_candidate(client):
    token = login(client)
    pid, ref, text = verified_policy_reference(client, token)
    r = create_numeric(client, token, pid, ref["id"], text)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["representation_state"] == "draft"
    assert body["review_state"] == "unreviewed"
    assert str(body["threshold_numeric"]).startswith("60")


def test_numeric_threshold_not_present_in_source_is_rejected(client):
    token = login(client)
    pid, ref, text = verified_policy_reference(client, token)
    r = create_numeric(client, token, pid, ref["id"], text, threshold="70")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "policy_criterion_source_unavailable"


def test_source_evidence_must_be_exact_source_passage(client):
    token = login(client)
    pid, ref, _text = verified_policy_reference(client, token)
    r = create_numeric(client, token, pid, ref["id"], "Someone typed 60 units per hectare")
    assert r.status_code == 409


def test_unverified_policy_reference_cannot_create_criterion(client):
    token = login(client)
    pid, ref, text = verified_policy_reference(client, token)
    # Create a second candidate reference but do not review it.
    search = client.post(f"/api/v1/projects/{pid}/document-search", headers=h(token), json={"query": "density 60"}).json()
    candidate = client.post(
        f"/api/v1/projects/{pid}/policy-references",
        headers=h(token),
        json={"citation": search["hits"][0]["citation"], "policy_statement": "Candidate only."},
    ).json()
    r = create_numeric(client, token, pid, candidate["id"], text, code="density.candidate")
    assert r.status_code == 409


def test_explicit_review_is_required_before_deterministic_use(client):
    token = login(client)
    pid, ref, text = verified_policy_reference(client, token)
    item = create_numeric(client, token, pid, ref["id"], text).json()
    use = client.post(f"/api/v1/projects/{pid}/policy-criteria/{item['id']}/resolve", headers=h(token))
    assert use.status_code == 409
    verified = client.post(
        f"/api/v1/projects/{pid}/policy-criteria/{item['id']}/review",
        headers=h(token),
        json={"action": "verify", "review_notes": "Rule shape checked against cited evidence."},
    )
    assert verified.status_code == 200, verified.text
    use = client.post(f"/api/v1/projects/{pid}/policy-criteria/{item['id']}/resolve", headers=h(token))
    assert use.status_code == 200, use.text
    assert use.json()["status"] == "validated"


def test_rejected_criterion_never_resolves(client):
    token = login(client)
    pid, ref, text = verified_policy_reference(client, token)
    item = create_numeric(client, token, pid, ref["id"], text).json()
    rejected = client.post(
        f"/api/v1/projects/{pid}/policy-criteria/{item['id']}/review",
        headers=h(token),
        json={"action": "reject", "review_notes": "Operator interpretation not supported."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["review_state"] == "rejected"
    assert client.post(f"/api/v1/projects/{pid}/policy-criteria/{item['id']}/resolve", headers=h(token)).status_code == 409


def test_final_criterion_rule_is_immutable_but_archivable(client):
    token = login(client)
    pid, ref, text = verified_policy_reference(client, token)
    item = create_numeric(client, token, pid, ref["id"], text).json()
    item = client.post(f"/api/v1/projects/{pid}/policy-criteria/{item['id']}/review", headers=h(token), json={"action": "verify"}).json()
    changed = client.patch(f"/api/v1/projects/{pid}/policy-criteria/{item['id']}", headers=h(token), json={"label": "Changed"})
    assert changed.status_code == 409
    archived = client.patch(f"/api/v1/projects/{pid}/policy-criteria/{item['id']}", headers=h(token), json={"is_archived": True})
    assert archived.status_code == 200 and archived.json()["is_archived"] is True
    assert client.post(f"/api/v1/projects/{pid}/policy-criteria/{item['id']}/resolve", headers=h(token)).status_code == 409


def test_cross_owner_criterion_is_missing_equivalent(client):
    a = login(client, "criterion-a@example.com")
    pid, ref, text = verified_policy_reference(client, a)
    item = create_numeric(client, a, pid, ref["id"], text).json()
    b = login(client, "criterion-b@example.com")
    r = client.get(f"/api/v1/projects/{pid}/policy-criteria/{item['id']}", headers=h(b))
    assert r.status_code == 404


def test_duplicate_code_within_project_is_rejected(client):
    token = login(client)
    pid, ref, text = verified_policy_reference(client, token)
    assert create_numeric(client, token, pid, ref["id"], text, code="density.limit").status_code == 201
    r = create_numeric(client, token, pid, ref["id"], text, code="density.limit")
    assert r.status_code == 409
