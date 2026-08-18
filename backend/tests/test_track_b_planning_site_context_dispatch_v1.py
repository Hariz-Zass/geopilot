import json
from pathlib import Path
from uuid import UUID, uuid4

from app.api.v1 import track_b
from app.schemas.track_b import TrackBPlannerDecisionResponse, TrackBPlannerDecisionRequest

PROJECT_ID = UUID("f7617e94-7d8c-47d0-8bed-635cf2f48579")
SITE_ID = UUID("2ea1e98d-347c-4a0a-8e5b-5dd7f9553673")
ANALYSIS_ID = uuid4()
QUESTION = "Apakah kemudahan pendidikan berhampiran tapak ini?"


def response_payload():
    return {
        "analysis_id": ANALYSIS_ID,
        "provider": "planning_orchestrator",
        "model": "evidence-router",
        "confidence": "moderate",
        "priority": "monitor",
        "decision_title": "Grounded planning evidence response",
        "issue": QUESTION,
        "planning_implication": "Validated evidence is available.",
        "evidence_summary": "Validated evidence used",
        "recommended_actions": [],
        "evidence_refs": ["context.site_surroundings"],
        "limitations": [],
        "planner_question": QUESTION,
        "evidence_architecture": "provenance_controlled",
        "evidence_policy": "provenance_controlled",
        "professional_review_required": True,
    }


def invoke(monkeypatch, tmp_path, route, *, helper=None, builder=None):
    manifest = Path(tmp_path) / "analysis.json"
    manifest.write_text(json.dumps({"site_id": str(SITE_ID)}), encoding="utf-8")
    calls = []

    monkeypatch.setattr(track_b, "list_track_b_datasets", lambda *args, **kwargs: [])
    monkeypatch.setattr(track_b, "route_question", lambda question: route)
    monkeypatch.setattr(track_b, "artifact_path", lambda *args: manifest)

    def fake_helper(*args, **kwargs):
        calls.append(("helper", kwargs))
        return helper or response_payload()

    def fake_builder(*args, **kwargs):
        calls.append(("builder", kwargs))
        return builder or response_payload()

    monkeypatch.setattr(track_b, "_run_track_b_planning_question", fake_helper)
    monkeypatch.setattr(track_b, "build_track_b_planner_decision", fake_builder)
    monkeypatch.setattr(
        track_b,
        "build_track_b_terrain_planner_decision",
        lambda *args, **kwargs: calls.append(("terrain", kwargs)) or response_payload(),
    )

    result = track_b.planner_decision_workspace(
        project_id=PROJECT_ID,
        analysis_id=ANALYSIS_ID,
        payload=TrackBPlannerDecisionRequest(planner_question=QUESTION),
        session=object(),
        current_user=object(),
    )
    return result, calls


def test_malay_site_context_uses_manifest_site_id_and_existing_helper(monkeypatch, tmp_path):
    route = track_b.route_question(QUESTION)
    result, calls = invoke(monkeypatch, tmp_path, route)

    assert route.capability == "site_context"
    assert route.tools == ("context.site_surroundings",)
    assert calls[0][0] == "helper"
    assert calls[0][1]["site_id"] == SITE_ID
    assert calls[0][1]["question"] == QUESTION
    assert TrackBPlannerDecisionResponse.model_validate(result).analysis_id == ANALYSIS_ID


def test_terrain_route_remains_specialized(monkeypatch, tmp_path):
    route = track_b.route_question("Berapa kecerunan tapak ini?")
    result, calls = invoke(monkeypatch, tmp_path, route)

    assert route.capability == "terrain_measurement"
    assert calls[0][0] == "terrain"
    assert TrackBPlannerDecisionResponse.model_validate(result).analysis_id == ANALYSIS_ID


def test_planning_multi_evidence_route_remains_helper(monkeypatch, tmp_path):
    route = track_b.route_question("Berapa kecerunan tapak ini dan zoning?")
    result, calls = invoke(monkeypatch, tmp_path, route)

    assert route.capability == "planning_multi_evidence"
    assert calls[0][0] == "helper"
    assert calls[0][1]["site_id"] == SITE_ID
    assert TrackBPlannerDecisionResponse.model_validate(result).analysis_id == ANALYSIS_ID


def test_documents_search_route_remains_helper(monkeypatch, tmp_path):
    route = track_b.route_question("What guideline applies to slope development?")
    result, calls = invoke(monkeypatch, tmp_path, route)

    assert "documents.search" in route.tools
    assert calls[0][0] == "helper"
    assert calls[0][1]["site_id"] == SITE_ID
    assert TrackBPlannerDecisionResponse.model_validate(result).analysis_id == ANALYSIS_ID


def test_temporal_route_keeps_track_b_fallback(monkeypatch, tmp_path):
    route = track_b.route_question("What changed between before and after?")
    result, calls = invoke(monkeypatch, tmp_path, route)

    assert route.capability == "temporal_change"
    assert calls[0][0] == "builder"
    assert TrackBPlannerDecisionResponse.model_validate(result).analysis_id == ANALYSIS_ID
    assert all(call[1].get("site_id") != SITE_ID for call in calls)
