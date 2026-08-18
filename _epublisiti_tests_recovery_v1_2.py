from pathlib import Path

tests = Path("/app/tests/test_planning_document_acquisition.py")
text = tests.read_text(encoding="utf-8-sig")

marker = "def test_epublisiti_adapter_v1_2("
if marker in text:
    print("SKIP: V1.2 tests already present.")
    raise SystemExit(0)

addition = '''
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
'''

tests.write_text(text.rstrip() + "\n\n" + addition + "\n", encoding="utf-8")
print("PATCHED:", tests)
