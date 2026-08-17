import httpx
import pytest

from app.services.planning_document_acquisition import (
    PlanMalaysiaOfficialProvider,
    PlanningDocumentAcquisitionError,
    PlanningDocumentCandidate,
    acquire_candidate,
    AcquiredPlanningDocument,
)


def candidate(uri: str) -> PlanningDocumentCandidate:
    return PlanningDocumentCandidate(
        document_class="GPP",
        title="Test Official GPP",
        authority="PLANMalaysia",
        jurisdiction="Malaysia",
        source_uri=uri,
        provider="planmalaysia_official",
        metadata={},
    )


def test_provider_supports_controlled_planning_classes_and_fails_closed():
    provider = PlanMalaysiaOfficialProvider()

    assert (
        provider.discover(
            document_class="RFN",
            jurisdiction="Malaysia",
            query="density",
        )
        == []
    )

    with pytest.raises(PlanningDocumentAcquisitionError):
        provider.discover(
            document_class="OTHER",
            jurisdiction=None,
            query="x",
        )


def test_downloader_rejects_non_official_host_before_network():
    with pytest.raises(PlanningDocumentAcquisitionError):
        acquire_candidate(candidate("https://example.com/test.pdf"))


def test_downloader_accepts_pdf_and_hashes_payload(monkeypatch):
    import app.services.planning_document_acquisition as mod

    monkeypatch.setattr(
        mod,
        "_public_dns_only",
        lambda host: None,
    )

    payload = b"%PDF-1.7\nGeoPilot\n%%EOF\n"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "myplan.planmalaysia.gov.my"
        return httpx.Response(
            200,
            content=payload,
            headers={"content-type": "application/pdf"},
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        result = acquire_candidate(
            candidate(
                "https://myplan.planmalaysia.gov.my/example.pdf"
            ),
            client=client,
        )

    assert result.content == payload
    assert result.mime_type == "application/pdf"
    assert len(result.checksum_sha256) == 64


def test_downloader_rejects_redirect_to_unapproved_host(monkeypatch):
    import app.services.planning_document_acquisition as mod

    monkeypatch.setattr(
        mod,
        "_public_dns_only",
        lambda host: None,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={
                "location": "https://example.com/file.pdf",
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(PlanningDocumentAcquisitionError):
            acquire_candidate(
                candidate(
                    "https://myplan.planmalaysia.gov.my/start"
                ),
                client=client,
            )


def test_epublisiti_adapter_v1_2(monkeypatch):
    import app.services.planning_document_acquisition as mod

    monkeypatch.setattr(mod, "_public_dns_only", lambda host: None)

    html = (
        '<html><body>'
        '<a href="/epublisiti/article?id=rt-1">DRAF RANCANGAN TEMPATAN DAERAH TEMERLOH 2035 (PENGGANTIAN)</a>'
        '<a href="/epublisiti/article?id=rsn-1">Draf Rancangan Struktur Negeri Terengganu 2050 (Kajian Semula)</a>'
        '<a href="/epublisiti/article?id=rkk-1">PUBLISITI DRAF RANCANGAN KAWASAN KHAS TASIK CHINI (PENGUBAHAN)</a>'
        '<a href="/epublisiti/article?id=comment">Ali on Draf Rancangan Tempatan Daerah Kulim 2035</a>'
        '</body></html>'
    )

    def handler(request):
        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html; charset=UTF-8"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = PlanMalaysiaOfficialProvider(client=client)

        rt = provider.discover(
            document_class="RT",
            jurisdiction="Pahang",
            query="Temerloh",
        )
        assert len(rt) == 1
        assert "draft" in rt[0].metadata["status_signals"]
        assert "replacement" in rt[0].metadata["status_signals"]
        assert rt[0].metadata["statutory_effect_verified"] is False

        rsn = provider.discover(
            document_class="RSN",
            jurisdiction="Terengganu",
            query="",
        )
        assert len(rsn) == 1
        assert "review" in rsn[0].metadata["status_signals"]

        rkk = provider.discover(
            document_class="RKK",
            jurisdiction="Pahang",
            query="Tasik Chini",
        )
        assert len(rkk) == 1
        assert "amendment" in rkk[0].metadata["status_signals"]
        assert "publicity" in rkk[0].metadata["status_signals"]


def test_epublisiti_unknown_jurisdiction_v1_2(monkeypatch):
    import app.services.planning_document_acquisition as mod

    monkeypatch.setattr(mod, "_public_dns_only", lambda host: None)

    def handler(request):
        return httpx.Response(
            200,
            text="<html></html>",
            headers={"content-type": "text/html"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = PlanMalaysiaOfficialProvider(client=client)
        with pytest.raises(PlanningDocumentAcquisitionError):
            provider.discover(
                document_class="RT",
                jurisdiction="Atlantis",
                query="",
            )


def test_rfn_remains_fail_closed_v1_2():
    provider = PlanMalaysiaOfficialProvider()
    assert provider.discover(
        document_class="RFN",
        jurisdiction="Malaysia",
        query="",
    ) == []


def test_epublisiti_pdf_resolution_v1(monkeypatch):
    import app.services.planning_document_acquisition as mod

    monkeypatch.setattr(mod, "_public_dns_only", lambda host: None)

    article = (
        '<html><body><table>'
        '<tr><td>1.</td><td>Laporan Draf RKK Tasik Chini</td>'
        '<td><a href="/portalassets/ePublisiti/main-report.pdf">Muat-Turun</a></td></tr>'
        '<tr><td>2.</td><td>Borang Bantahan</td>'
        '<td><a href="/portalassets/ePublisiti/form.pdf">Muat-Turun</a></td></tr>'
        '<tr><td>3.</td><td>Website</td>'
        '<td><a href="https://example.com/evil.pdf">Muat-Turun</a></td></tr>'
        '</table></body></html>'
    )

    def handler(request):
        return httpx.Response(
            200,
            text=article,
            headers={"content-type": "text/html"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = PlanMalaysiaOfficialProvider(client=client)
        candidate = PlanningDocumentCandidate(
            document_class="RKK",
            title="Draf Rancangan Kawasan Khas Tasik Chini",
            authority="PLANMalaysia",
            jurisdiction="Pahang",
            source_uri="https://www.planmalaysia.gov.my/epublisiti/article?id=rkk-test",
            provider="planmalaysia_official",
            metadata={"document_status": "unverified"},
        )
        links = provider.resolve_candidate_pdf_links(candidate)

    assert len(links) == 2
    assert links[0].source_uri.endswith("main-report.pdf")
    assert "Laporan Draf RKK Tasik Chini" in links[0].title
    assert links[0].metadata["parent_article_uri"] == candidate.source_uri


def test_gpp_direct_pdf_resolution_v1(monkeypatch):
    import app.services.planning_document_acquisition as mod

    monkeypatch.setattr(mod, "_public_dns_only", lambda host: None)
    provider = PlanMalaysiaOfficialProvider()
    candidate = PlanningDocumentCandidate(
        document_class="GPP",
        title="GPP Test",
        authority="PLANMalaysia",
        jurisdiction=None,
        source_uri="https://www.planmalaysia.gov.my/uploads/content-downloads/test.pdf",
        provider="planmalaysia_official",
        metadata={},
    )
    assert provider.resolve_candidate_pdf_links(candidate) == [candidate]

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
        content=b"%PDF-1.7\nGeoPilot\n%%EOF\n",
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
        mod, "ingest_acquired_pdf",
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
        content=b"%PDF-1.7\nGeoPilot\n%%EOF\n",
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
