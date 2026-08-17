from pathlib import Path

def test_gis_area_explicit_site_state_opt_in():
    text=Path("app/services/gis_analysis.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert "site_state=site_state" in text
    assert "if site_state is SiteState.ACTIVE" in text
    assert "AND s.is_archived IS FALSE" in text

def test_applicability_explicit_site_state_opt_in():
    text=Path("app/services/site_applicability.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert "site_state=site_state" in text

def test_planning_tools_propagate_site_state():
    text=Path("app/services/planning_tools.py").read_text(encoding="utf-8-sig")
    assert text.count("site_state: SiteState = SiteState.ACTIVE") >= 2
    assert text.count("site_state=site_state") >= 2

def test_orchestrator_propagates_existing_track_b_site_state():
    text=Path("app/services/planning_orchestrator.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert text.count("site_state=site_state") >= 3

def test_terrain_available_behavior_remains():
    text=Path("app/services/terrain_analysis.py").read_text(encoding="utf-8-sig")
    assert "site_state=SiteState.AVAILABLE" in text
