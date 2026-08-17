from pathlib import Path

def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig")

def test_closed_mode_removed_from_backend_architecture():
    paths = [
        "app/core/config.py",
        "app/services/track_b.py",
        "app/services/track_b_acceptance.py",
        "app/services/track_b_ai.py",
        "app/services/track_b_workflow.py",
    ]
    text = "\n".join(read(p) for p in paths).casefold()
    for forbidden in (
        "track_b_competition_mode",
        "closed-evidence",
        "closed track b evidence boundary",
        "external acquisition is disabled",
    ):
        assert forbidden not in text

def test_provenance_architecture_present():
    assert "provenance_controlled" in read("app/services/track_b_acceptance.py")
    assert "provenance_controlled" in read("app/services/track_b_ai.py")
    assert "provenance_controlled" in read("app/services/track_b_workflow.py")

def test_anti_hallucination_and_numeric_grounding_preserved():
    ai = read("app/services/track_b_ai.py")
    assert "Never invent" in ai
    assert "NUMERIC GROUNDING RULE" in ai
    assert "_validate_no_invented_numbers" in ai
    assert "_validate_decision_numbers" in ai

def test_terrain_and_auto_research_markers_preserved():
    ai = read("app/services/track_b_ai.py")
    orchestrator = read("app/services/planning_orchestrator.py")
    assert "TRACKB_TERRAIN_DECISION_ROUTER_V2" in ai
    assert "terrain.site_summary" in ai
    assert "AUTO_RESEARCH_QUESTION_ROUTER_V1" in orchestrator
    assert "AUTO_RESEARCH_EVIDENCE_BRIDGE_V1" in orchestrator
