from pathlib import Path

def test_site_applicability_available_sql_gate_is_parameterized():
    text = Path("app/services/site_applicability.py").read_text(encoding="utf-8-sig")
    assert "CAST(:require_active AS boolean) IS FALSE" in text
    assert "OR s.is_active IS TRUE" in text
    assert '"require_active": site_state is SiteState.ACTIVE' in text

def test_site_applicability_archived_gate_remains():
    text = Path("app/services/site_applicability.py").read_text(encoding="utf-8-sig")
    assert "AND s.is_archived IS FALSE" in text

def test_site_state_still_flows_through_python_scope():
    text = Path("app/services/site_applicability.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert "site_state=site_state" in text
