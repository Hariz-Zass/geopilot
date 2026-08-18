from app.services.planning_document_auto_research import (
    infer_document_classes,
    infer_jurisdiction,
)


def test_auto_research_classifies_density_as_rt_and_gpp():
    classes = infer_document_classes(
        "Apakah densiti pembangunan yang dibenarkan dalam rancangan tempatan dan GPP?"
    )
    assert "RT" in classes
    assert "GPP" in classes


def test_auto_research_classifies_rkk():
    assert "RKK" in infer_document_classes(
        "Apakah kawalan RKK Tasik Chini untuk kawasan ini?"
    )


def test_auto_research_rfn_stays_explicit():
    assert "RFN" in infer_document_classes(
        "Apakah dasar Rancangan Fizikal Negara yang berkaitan?"
    )


def test_auto_research_detects_malaysian_state():
    assert (
        infer_jurisdiction("Semak Rancangan Tempatan di Ipoh, Perak")
        == "Perak"
    )


def test_auto_research_does_not_guess_jurisdiction():
    assert (
        infer_jurisdiction(
            "Semak rancangan tempatan untuk kawasan tersebut"
        )
        is None
    )
