from app.services.planning_document_acquisition import (
    PlanningDocumentCandidate,
    _rank_epublisiti_candidates,
    _rank_catalogue_candidates,
)


def c(title, cls, jurisdiction="Perak"):
    return PlanningDocumentCandidate(
        document_class=cls,
        title=title,
        authority="PLANMalaysia",
        jurisdiction=jurisdiction,
        source_uri="https://www.planmalaysia.gov.my/epublisiti/article?id=test",
        provider="planmalaysia_official",
        metadata={"document_status": "unverified"},
    )


def test_rsn_perak_generic_question_matches_explicit_state_titles():
    items = [
        c("LAPORAN TINJAUAN RANCANGAN STRUKTUR NEGERI PERAK 2040 (KAJIAN SEMULA)", "RSN"),
        c("Draf Rancangan Struktur Negeri Perak 2040", "RSN"),
    ]
    q = "Apakah dasar pembangunan negeri yang dinyatakan dalam Rancangan Struktur Negeri Perak?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RSN", jurisdiction="Perak"
    )
    assert len(ranked) == 2
    assert ranked[0].title == "Draf Rancangan Struktur Negeri Perak 2040"


def test_rt_ipoh_does_not_substitute_other_locality():
    items = [
        c("Draf Rancangan Tempatan Daerah Perak Tengah 2030", "RT"),
        c("Draf Rancangan Tempatan Daerah Hulu Perak 2030", "RT"),
    ]
    q = "Apakah dasar dan cadangan guna tanah dalam Rancangan Tempatan bagi kawasan Ipoh?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RT", jurisdiction="Perak"
    )
    assert ranked == []


def test_rt_perak_tengah_requires_tengah_not_merely_perak_or_year():
    items = [
        c("Draf Rancangan Tempatan Daerah Perak Tengah 2030", "RT"),
        c("Draf Rancangan Tempatan Daerah Hulu Perak 2030", "RT"),
    ]
    q = "Apakah kandungan Rancangan Tempatan Daerah Perak Tengah 2030?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RT", jurisdiction="Perak"
    )
    assert len(ranked) == 1
    assert "Perak Tengah" in ranked[0].title


def test_rt_specific_locality_can_match_without_state_name_in_title():
    items = [
        c("Rancangan Tempatan Daerah Manjung 2040", "RT"),
        c("Rancangan Tempatan Daerah Hulu Perak 2030", "RT"),
    ]
    q = "Apakah kandungan Rancangan Tempatan Daerah Manjung 2040?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RT", jurisdiction="Perak"
    )
    assert len(ranked) == 1
    assert "Manjung" in ranked[0].title


def test_generic_rt_perak_fails_closed_when_title_does_not_prove_state():
    items = [
        c("Rancangan Tempatan Daerah Manjung 2040", "RT"),
        c("Rancangan Tempatan Daerah Setiu 2035", "RT"),
    ]
    q = "Apakah kandungan Rancangan Tempatan di negeri Perak?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RT", jurisdiction="Perak"
    )
    assert ranked == []


def test_generic_rkk_perak_fails_closed_without_state_in_title():
    items = [
        c("Rancangan Kawasan Khas Tasik Chini (Pengubahan)", "RKK"),
        c("Rancangan Kawasan Khas Rangkaian Ekologi Central Forest Spine", "RKK"),
    ]
    q = "Apakah cadangan dalam Rancangan Kawasan Khas di negeri Perak?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RKK", jurisdiction="Perak"
    )
    assert ranked == []


def test_gpp_v1_ranker_behavior_is_preserved():
    items = [
        c("(02) GP007 A(11)GPP Pembangunan Di Kawasan Bukit dan Tanah Tinggi", "GPP", jurisdiction=None),
        c("(22) GP012 GPP Papan Tanda Premis Perniagaan", "GPP", jurisdiction=None),
    ]
    ranked = _rank_catalogue_candidates(items, "bukit tanah tinggi")
    assert len(ranked) == 1
    assert "Bukit dan Tanah Tinggi" in ranked[0].title