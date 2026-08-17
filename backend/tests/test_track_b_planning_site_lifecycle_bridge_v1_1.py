from pathlib import Path
import inspect

from app.services.isolation import SiteState, resolve_analysis_scope
from app.services.planning_runs import create_planning_run, get_planning_run
from app.services.planning_orchestrator import execute_planning_run


def test_defaults_remain_active():
    assert inspect.signature(resolve_analysis_scope).parameters["site_state"].default is SiteState.ACTIVE
    assert inspect.signature(create_planning_run).parameters["site_state"].default is SiteState.ACTIVE
    assert inspect.signature(get_planning_run).parameters["site_state"].default is SiteState.ACTIVE
    assert inspect.signature(execute_planning_run).parameters["site_state"].default is SiteState.ACTIVE


def test_track_b_helper_explicitly_opts_into_available():
    text=Path("app/api/v1/track_b.py").read_text(encoding="utf-8-sig")
    start=text.index("def _run_track_b_planning_question(")
    end=text.index("\n\n@router.post",start)
    block=text[start:end]
    assert block.count("site_state=SiteState.AVAILABLE")==2


def test_available_still_rejects_archived_site():
    text=Path("app/services/isolation.py").read_text(encoding="utf-8-sig")
    assert "site_state in {SiteState.AVAILABLE, SiteState.ACTIVE} and site.is_archived" in text
    assert 'raise ScopeStateError("site is archived")' in text


def test_active_still_rejects_inactive_site():
    text=Path("app/services/isolation.py").read_text(encoding="utf-8-sig")
    assert "site_state is SiteState.ACTIVE and not site.is_active" in text
    assert 'raise ScopeStateError("site is inactive")' in text
