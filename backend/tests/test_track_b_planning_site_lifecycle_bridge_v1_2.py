from pathlib import Path
import inspect

from app.schemas.planning_run import PlanningRunCreate
from app.services.isolation import SiteState
from app.services.planning_runs import create_planning_run
from app.services.planning_orchestrator import execute_planning_run


def test_planning_run_create_has_no_site_state_field():
    assert "site_state" not in PlanningRunCreate.model_fields


def test_track_b_helper_passes_available_to_service_not_schema():
    text = Path("app/api/v1/track_b.py").read_text(encoding="utf-8-sig")
    start = text.index("def _run_track_b_planning_question(")
    end = text.index("\n\n@router.post", start)
    block = text[start:end]

    assert "PlanningRunCreate(question=question, development_intent=None, site_state=" not in block
    assert "PlanningRunCreate(question=question, development_intent=None), site_state=SiteState.AVAILABLE" in block
    assert "execute_planning_run(" in block
    assert block.count("site_state=SiteState.AVAILABLE") == 2


def test_service_defaults_remain_active():
    assert inspect.signature(create_planning_run).parameters["site_state"].default is SiteState.ACTIVE
    assert inspect.signature(execute_planning_run).parameters["site_state"].default is SiteState.ACTIVE
