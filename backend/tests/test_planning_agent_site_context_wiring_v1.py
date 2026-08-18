from app.services.data_requirement_router import route_question
from app.services.planning_tools import APPROVED_TOOLS


def test_site_context_tool_registered():
    spec = APPROVED_TOOLS["context.site_surroundings"]
    assert spec.domain == "context"
    assert spec.deterministic is False
    assert spec.read_only is True


def test_routes_malay_nearby_education_question():
    route = route_question(
        "Apakah kemudahan pendidikan berhampiran tapak ini?"
    )
    assert route.state == "planned"
    assert route.capability == "site_context"
    assert route.tools == ("context.site_surroundings",)


def test_routes_english_nearby_facilities_question():
    route = route_question(
        "What facilities are available near this site?"
    )
    assert route.state == "planned"
    assert route.capability == "site_context"
    assert route.tools == ("context.site_surroundings",)


def test_routes_access_context_question():
    route = route_question(
        "Apakah akses pengangkutan di sekitar kawasan ini?"
    )
    assert route.capability == "site_context"
    assert route.tools == ("context.site_surroundings",)


def test_terrain_measurement_not_hijacked():
    route = route_question(
        "berapa slope tertinggi di kawasan ini"
    )
    assert route.capability == "terrain_measurement"
    assert route.tools == ("terrain.site_summary",)


def test_policy_question_not_hijacked():
    route = route_question(
        "What guideline applies to slope development?"
    )
    assert route.capability == "terrain_policy"
    assert route.tools == ("documents.search",)
