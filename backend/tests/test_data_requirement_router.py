from app.services.data_requirement_router import route_question
from app.services.planning_orchestrator import _plan


def test_slope_question_fails_closed_and_requires_dem():
    route = route_question("berapa slope tertinggi di kawasan ini")
    assert route.state == "planned"
    assert route.capability == "terrain_measurement"
    assert route.tools == ("terrain.site_summary",)
    assert route.required_evidence == ("project_site_dem_or_elevation_raster",)
    joined = " ".join(route.limitations).casefold()
    assert "dem" in joined
    assert "ndvi" in joined


def test_english_elevation_question_requires_terrain_evidence():
    route = route_question("What is the maximum elevation of this site?")
    assert route.state == "planned"
    assert route.capability == "terrain_measurement"


def test_terrain_policy_only_question_keeps_document_search():
    route = route_question("What guideline applies to slope development?")
    assert route.state == "planned"
    assert route.capability == "terrain_policy"
    assert route.tools == ("documents.search",)


def test_existing_area_and_site_routing_is_preserved():
    state, tools = _plan("What is the area and land use of this site?")
    assert state == "planned"
    assert "gis.site_area" in tools
    assert "gis.site_applicability" in tools
    assert "documents.search" in tools


def test_density_ambiguity_guard_is_preserved():
    route = route_question("berapa density")
    assert route.state == "clarification_required"
    assert route.tools == ()
    assert route.limitations


def test_generic_planning_question_does_not_invent_terrain_tool():
    route = route_question("What planning evidence is available for this site?")
    assert route.state == "planned"
    assert "documents.search" in route.tools
    assert all(not tool.startswith("terrain.") for tool in route.tools)

def test_malay_maximum_height_routes_to_terrain_measurement():
    route = route_question("Berapakah ketinggian maksimum kawasan tersebut?")
    assert route.state == "planned"
    assert route.capability == "terrain_measurement"
    assert route.tools == ("terrain.site_summary",)


def test_malay_maximum_elevation_routes_to_terrain_measurement():
    route = route_question("Berapa elevasi tertinggi kawasan ini?")
    assert route.capability == "terrain_measurement"
    assert route.tools == ("terrain.site_summary",)


def test_malay_average_slope_routes_to_terrain_measurement():
    route = route_question("Berapakah purata kecerunan kawasan ini?")
    assert route.capability == "terrain_measurement"
    assert route.tools == ("terrain.site_summary",)


def test_ndvi_question_does_not_route_to_terrain_measurement():
    route = route_question("Berapakah perubahan NDVI antara imej before dan after?")
    assert route.capability != "terrain_measurement"
    assert all(not tool.startswith("terrain.") for tool in route.tools)

