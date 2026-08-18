from pathlib import Path

path = Path("/app/tests/test_planning_document_acquisition.py")
text = path.read_text(encoding="utf-8-sig")

if "test_epublisiti_pdf_resolution_v1" in text:
    print("SKIP: PDF resolver tests already present.")
    raise SystemExit(0)

addition = '''
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
'''

path.write_text(text.rstrip() + "\n\n" + addition + "\n", encoding="utf-8")
print("PATCHED:", path)
