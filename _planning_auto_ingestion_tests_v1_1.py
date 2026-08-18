from pathlib import Path

path = Path("/app/tests/test_planning_document_acquisition.py")
text = path.read_text(encoding="utf-8-sig")

if "test_auto_ingestion_v1_1_registers_acquired_document" in text:
    print("SKIP: V1.1 auto-ingestion tests already installed.")
    raise SystemExit(0)

addition = """
def test_auto_ingestion_v1_1_registers_acquired_document(monkeypatch):
    import uuid
    import app.services.planning_document_acquisition as mod

    class Obj:
        pass

    document = Obj()
    document.id = uuid.uuid4()
    version = Obj()
    version.id = uuid.uuid4()
    captured = {}

    def fake_create(session, *, owner, project_id, request):
        captured["request"] = request
        return document, version

    monkeypatch.setattr(mod, "create_planning_document", fake_create)

    candidate = PlanningDocumentCandidate(
        document_class="GPP",
        title="GPP Test",
        authority="PLANMalaysia",
        jurisdiction=None,
        source_uri="https://www.planmalaysia.gov.my/uploads/test.pdf",
        provider="planmalaysia_official",
        metadata={"document_status": "unverified"},
    )
    acquired = AcquiredPlanningDocument(
        candidate=candidate,
        content=b"%PDF-1.7\\nGeoPilot\\n%%EOF\\n",
        mime_type="application/pdf",
        checksum_sha256="a" * 64,
        final_uri=candidate.source_uri,
    )

    doc, ver = mod.register_acquired_document(
        object(), owner=object(), project_id=uuid.uuid4(), acquired=acquired
    )
    assert doc is document
    assert ver is version
    req = captured["request"]
    assert req.initial_version.source_kind == "acquired"
    assert req.initial_version.source_uri == candidate.source_uri
    assert req.initial_version.checksum_sha256 == "a" * 64
    assert req.initial_version.review_state == "requires_review"


def test_auto_ingestion_v1_1_pipeline_calls_existing_layers(monkeypatch):
    import uuid
    import app.services.planning_document_acquisition as mod

    class Obj:
        pass

    document = Obj()
    document.id = uuid.uuid4()
    version = Obj()
    version.id = uuid.uuid4()
    ingestion = Obj()
    ingestion.version = version
    calls = []

    monkeypatch.setattr(
        mod, "register_acquired_document", lambda *a, **k: (document, version)
    )
    monkeypatch.setattr(
        mod, "ingest_registered_pdf",
        lambda *a, **k: (calls.append("ingest") or ingestion),
    )
    monkeypatch.setattr(
        mod, "build_document_chunks",
        lambda *a, **k: (calls.append("chunks") or "chunks"),
    )
    monkeypatch.setattr(
        mod, "build_document_embedding_index",
        lambda *a, **k: (calls.append("index") or "index"),
    )

    candidate = PlanningDocumentCandidate(
        document_class="RT",
        title="RT Test",
        authority="PLANMalaysia",
        jurisdiction="Perak",
        source_uri="https://www.planmalaysia.gov.my/uploads/test.pdf",
        provider="planmalaysia_official",
        metadata={},
    )
    acquired = AcquiredPlanningDocument(
        candidate=candidate,
        content=b"%PDF-1.7\\nGeoPilot\\n%%EOF\\n",
        mime_type="application/pdf",
        checksum_sha256="b" * 64,
        final_uri=candidate.source_uri,
    )

    result = mod.ingest_acquired_document(
        object(), owner=object(), project_id=uuid.uuid4(), acquired=acquired
    )
    assert calls == ["ingest", "chunks", "index"]
    assert result["chunks"] == "chunks"
    assert result["index"] == "index"
"""

path.write_text(text.rstrip() + "\n\n" + addition.strip() + "\n", encoding="utf-8")
print("PATCHED:", path)
