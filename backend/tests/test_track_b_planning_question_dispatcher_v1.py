from types import SimpleNamespace
import uuid

def test_planning_run_adapter_preserves_track_b_contract():
    from app.api.v1.track_b import _planning_run_to_track_b_decision
    analysis_id = uuid.uuid4()
    run = SimpleNamespace(status="completed", synthesis="The retrieved GPP states the grounded planning requirement.", provider_metadata={"provider": "openai", "model": "test-model"}, limitations=[], evidence=[{"tool_name": "documents.search", "payload": {"citation_label": "GPP Test â€” p. 12", "document_title": "GPP Test"}}])
    result = _planning_run_to_track_b_decision(analysis_id=analysis_id, question="What does the GPP state?", run=run)
    assert result["analysis_id"] == analysis_id
    assert result["provider"] == "openai"
    assert result["model"] == "test-model"
    assert result["confidence"] == "moderate"
    assert result["priority"] == "monitor"
    assert result["planning_implication"] == run.synthesis
    assert result["evidence_refs"] == ["GPP Test â€” p. 12"]
    assert result["evidence_architecture"] == "provenance_controlled"

def test_planning_run_adapter_degrades_safely_without_synthesis():
    from app.api.v1.track_b import _planning_run_to_track_b_decision
    result = _planning_run_to_track_b_decision(analysis_id=uuid.uuid4(), question="What policy applies?", run=SimpleNamespace(status="degraded", synthesis=None, provider_metadata={}, limitations=["No matching official document evidence was found."], evidence=[]))
    assert result["confidence"] == "limited"
    assert result["priority"] == "evidence_limited"
    assert result["limitations"]

def test_track_b_api_dispatcher_reuses_planning_orchestrator():
    from pathlib import Path
    text = Path("app/api/v1/track_b.py").read_text(encoding="utf-8-sig")
    assert "TRACKB_PLANNING_QUESTION_DISPATCHER_V1" in text
    assert '"documents.search" in route.tools' in text
    assert "create_planning_run(" in text
    assert "execute_planning_run(" in text
    assert "build_track_b_terrain_planner_decision(" in text
    assert "build_track_b_planner_decision(" in text
