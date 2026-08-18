from pathlib import Path

path = Path("/app/tests/test_planning_document_acquisition.py")
text = path.read_text(encoding="utf-8-sig")

if "test_auto_ingestion_v1_registers_acquired_document" in text:
    print("SKIP: auto-ingestion tests already installed.")
    raise SystemExit(0)

addition = r'''

def test_auto_ingestion_v1_registers_acquired_document(monkeypatch):
    import app.services.planning_document_acquisition as mod

    class Obj:
        pass

    created_document = Obj()
    created_document.id = __import__("uuid").uuid4()
    created_version = Obj()
    created_version.id = __import__("uuid").uuid4()

    captured = {}

    def fake_create(session, *, owner, project_id, request):
        captured["request"] = request
        return created_document, created_version

    monkeypatch.setattr(mod, "create_planning_document", fake_create)

    candidate = PlanningDocumentCandidate(
        document_class="GPP",
        title="GPP Kejiranan Hijau",
        authority="PLANMalaysia",
        jurisdiction=None,
        source_uri="https://www.planmalaysia.gov.my/uploads/test.pdf",
        provider="planmalaysia_official",
        metadata={
            "document_status": "unverified",
            "statutory_effect_verified": False,
        },
    )
    acquired = AcquiredPlanningDocument(
        candidate=candidate,
        content=b"%PDF-1.7\nGeoPilot\n%%EOF\n",
        mime_type="application/pdf",
        checksum_sha256="a" * 64,
        final_uri=candidate.source_uri,
    )

    doc, ver = mod.register_acquired_document(
        object(),
        owner=object(),
        project_id=__import__("uuid").uuid4(),
        acquired=acquired,
    )

    assert doc is created_document
    assert ver is created_version
    req = captured["request"]
    assert req.initial_version.source_kind == "acquired"
    assert req.initial_version.source_uri == candidate.source_uri
    assert req.initial_version.checksum_sha256 == "a" * 64
    assert req.initial_version.review_state == "requires_review"
    assert req.initial_version.provenance["provider"] == "planmalaysia_official"


def test_auto_ingestion_v1_pipeline_calls_existing_layers(monkeypatch):
    import app.services.planning_document_acquisition as mod

    class Obj:
        pass

    document = Obj()
    document.id = __import__("uuid").uuid4()
    version = Obj()
    version.id = __import__("uuid").uuid4()

    ingestion = Obj()
    ingestion.version = version

    calls = []

    monkeypatch.setattr(
        mod,
        "register_acquired_document",
        lambda *a, **k: (document, version),
    )

    def fake_ingest(*args, **kwargs):
        calls.append("ingest")
        return ingestion

    def fake_chunks(*args, **kwargs):
        calls.append("chunks")
        return "chunk-summary"

    def fake_index(*args, **kwargs):
        calls.append("index")
        return "index-object"

    monkeypatch.setattr(mod, "ingest_registered_pdf", fake_ingest)
    monkeypatch.setattr(mod, "build_document_chunks", fake_chunks)
    monkeypatch.setattr(mod, "build_document_embedding_index", fake_index)

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
        content=b"%PDF-1.7\nGeoPilot\n%%EOF\n",
        mime_type="application/pdf",
        checksum_sha256="b" * 64,
        final_uri=candidate.source_uri,
    )

    result = mod.ingest_acquired_document(
        object(),
        owner=object(),
        project_id=__import__("uuid").uuid4(),
        acquired=acquired,
    )

    assert calls == ["ingest", "chunks", "index"]
    assert result["chunks"] == "chunk-summary"
    assert result["index"] == "index-object"
'''

path.write_text(text.rstrip() + "

" + addition + "
", encoding="utf-8")
print("PATCHED:", path)
