from app.services.data_requirement_router import route_question

def test_area_terrain_without_zoning_stays_two_tools():
    r=route_question("Apakah keluasan tapak dan keadaan terrain termasuk elevation dan slope?")
    assert r.capability=="planning_multi_evidence"
    assert r.tools==("gis.site_area","terrain.site_summary")

def test_terrain_zoning_adds_applicability_and_documents():
    r=route_question("Apakah terrain termasuk elevation dan slope serta zoning yang terpakai kepada tapak ini?")
    assert r.capability=="planning_multi_evidence"
    assert r.tools==("terrain.site_summary","gis.site_applicability","documents.search")

def test_area_terrain_zoning_adds_all_tools():
    r=route_question("Apakah keluasan tapak, terrain termasuk elevation dan slope, serta zoning, guna tanah atau planning area yang terpakai kepada tapak ini?")
    assert r.capability=="planning_multi_evidence"
    assert r.tools==("gis.site_area","terrain.site_summary","gis.site_applicability","documents.search")

def test_zoning_only_route_preserved():
    r=route_question("Apakah zoning atau guna tanah yang terpakai kepada tapak ini?")
    assert r.capability=="planning_general"
    assert r.tools==("gis.site_applicability","documents.search")

def test_pure_terrain_preserved():
    r=route_question("Berapakah slope maksimum dan elevation purata?")
    assert r.capability=="terrain_measurement"
    assert r.tools==("terrain.site_summary",)

def test_terrain_policy_precedence_preserved():
    r=route_question("Apakah garis panduan pembangunan cerun dan slope yang terpakai?")
    assert r.capability=="terrain_policy"
    assert r.tools==("documents.search",)
