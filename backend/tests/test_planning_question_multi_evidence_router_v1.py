from pathlib import Path
from app.services.data_requirement_router import route_question

def test_mixed_area_and_terrain_routes_to_both_tools():
    q = (
        "Berdasarkan kawasan tapak yang dipilih, apakah keluasan tapak, "
        "keadaan terrain termasuk elevation dan slope?"
    )
    r = route_question(q)
    assert r.state == "planned"
    assert r.capability == "planning_multi_evidence"
    assert r.tools == ("gis.site_area", "terrain.site_summary")

def test_pure_terrain_measurement_preserves_direct_route():
    r = route_question("Berapakah slope maksimum dan elevation purata tapak ini?")
    assert r.capability == "terrain_measurement"
    assert r.tools == ("terrain.site_summary",)

def test_general_area_question_still_uses_site_area():
    r = route_question("Berapakah keluasan tapak ini?")
    assert "gis.site_area" in r.tools

def test_track_b_dispatcher_sends_multi_evidence_to_planning_orchestrator():
    text = Path("app/api/v1/track_b.py").read_text(encoding="utf-8-sig")
    assert 'route.capability == "planning_multi_evidence"' in text
    assert '"documents.search" in route.tools' in text

def test_policy_precedence_is_preserved():
    r = route_question("Apakah garis panduan pembangunan cerun dan slope yang terpakai?")
    assert r.capability == "terrain_policy"
    assert r.tools == ("documents.search",)
