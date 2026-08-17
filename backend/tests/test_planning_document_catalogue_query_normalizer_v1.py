from app.services.planning_document_acquisition import PlanningDocumentCandidate, _catalogue_terms, _rank_catalogue_candidates

def c(title, cls="GPP"):
    return PlanningDocumentCandidate(
        document_class=cls,
        title=title,
        authority="PLANMalaysia",
        jurisdiction=None,
        source_uri="https://www.planmalaysia.gov.my/uploads/test.pdf",
        provider="planmalaysia_official",
        metadata={},
    )

def test_full_question_reduces_to_meaningful_terms():
    q=("Apakah garis panduan pembangunan di kawasan bukit dan tanah tinggi? "
       "Nyatakan syarat atau parameter yang dinyatakan dalam GPP rasmi PLANMalaysia "
       "dan sertakan sumber bukti. Jangan reka maklumat yang tidak terdapat dalam dokumen.")
    terms=_catalogue_terms(q)
    for expected in ("pembangunan","bukit","tanah","tinggi","syarat","parameter"):
        assert expected in terms
    for rejected in ("apakah","nyatakan","sumber","bukti","planmalaysia","jangan","reka","maklumat"):
        assert rejected not in terms

def test_full_question_ranks_correct_gpp_first():
    q=("Apakah garis panduan pembangunan di kawasan bukit dan tanah tinggi? "
       "Nyatakan syarat atau parameter yang dinyatakan dalam GPP rasmi PLANMalaysia dan sertakan sumber bukti.")
    items=[
        c("(02) GP007 A(11)GPP Pembangunan Di Kawasan Bukit dan Tanah Tinggi"),
        c("(18) GP007 A (1) GPP Pemuliharaan Dan Pembangunan Kawasan Sensitif Alam Sekitar (KSAS)"),
        c("(22) GP012 GPP Papan Tanda Premis Perniagaan"),
    ]
    ranked=_rank_catalogue_candidates(items,q)
    assert ranked
    assert "Bukit dan Tanah Tinggi" in ranked[0].title

def test_short_query_still_matches():
    items=[c("(02) GP007 A(11)GPP Pembangunan Di Kawasan Bukit dan Tanah Tinggi"),c("(22) GP012 GPP Papan Tanda Premis Perniagaan")]
    ranked=_rank_catalogue_candidates(items,"bukit tanah tinggi")
    assert len(ranked)==1

def test_zero_overlap_fails_closed():
    assert _rank_catalogue_candidates([c("(22) GP012 GPP Papan Tanda Premis Perniagaan")],"bukit tanah tinggi")==[]

def test_generic_rt_question_matches_title_terms():
    rt=c("Rancangan Tempatan Daerah Ipoh 2035",cls="RT")
    ranked=_rank_catalogue_candidates([rt],"Apakah densiti yang dinyatakan dalam Rancangan Tempatan Daerah Ipoh 2035?")
    assert ranked==[rt]
