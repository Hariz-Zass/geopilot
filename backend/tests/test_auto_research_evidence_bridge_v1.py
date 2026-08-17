from pathlib import Path


def test_auto_research_evidence_bridge_is_wired():
    text = Path("app/services/planning_orchestrator.py").read_text(encoding="utf-8")
    assert "AUTO_RESEARCH_QUESTION_ROUTER_V1" in text
    assert "AUTO_RESEARCH_EVIDENCE_BRIDGE_V1" in text
    assert "auto_research_document_ids = list(auto_research.document_ids)" in text
    assert "elif auto_research_document_ids:" in text


def test_bridge_preserves_fail_closed_when_no_document_candidates():
    text = Path("app/services/planning_orchestrator.py").read_text(encoding="utf-8")
    assert "applicable_document_ids = []" in text


def test_bridge_preserves_document_search():
    text = Path("app/services/planning_orchestrator.py").read_text(encoding="utf-8")
    assert "_document_search_evidence(" in text
    assert 'if "documents.search" in tools:' in text
