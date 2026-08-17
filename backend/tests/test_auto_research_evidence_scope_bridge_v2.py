from pathlib import Path


def test_no_spatial_evidence_uses_auto_research_document_scope():
    text = Path("app/services/planning_orchestrator.py").read_text(
        encoding="utf-8-sig"
    )
    marker = "# AUTO_RESEARCH_EVIDENCE_SCOPE_BRIDGE_V2"
    assert marker in text

    start = text.index(marker)
    block = text[start:start + 900]

    assert "applicable_document_ids = list(auto_research_document_ids)" in block
    assert "document_ids=(" in text
    assert "applicable_document_ids" in text


def test_bridge_does_not_replace_existing_spatial_merge_logic():
    text = Path("app/services/planning_orchestrator.py").read_text(
        encoding="utf-8-sig"
    )

    assert "*resolved_document_ids" in text
    assert "*auto_research_document_ids" in text
    assert "resolved_document_ids" in text