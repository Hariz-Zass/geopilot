from pathlib import Path
from app.services.track_b_smart_site_discovery import _candidate

def ds(name,count,types,features):
    return {"logical_name":name,"format":"geopackage","source_checksum_sha256":"0"*64,"normalized":{"normalized_crs":"EPSG:4326","feature_count":count,"geometry_types":types,"geojson":{"type":"FeatureCollection","features":features}}}

def poly():
    return {"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[101,3],[101.01,3],[101.01,3.01],[101,3.01],[101,3]]]}}

def test_strong_boundary_candidate():
    c=_candidate(ds("SEMP_TAPAK",1,["Polygon"],[poly()]))
    assert c["candidate_status"]=="strong_site_boundary_candidate"
    assert c["requires_confirmation"] is True

def test_large_lot_layer_not_auto_site():
    c=_candidate(ds("Ndcdb_lot",374539,["Polygon"],[poly()]))
    assert c["candidate_status"]=="large_polygon_reference_layer"

def test_empty_boundary_hint_preserved():
    c=_candidate(ds("SEMP_TAPAK",0,[],[]))
    assert c["candidate_status"]=="empty_boundary_candidate"

def test_line_layer_not_site_candidate():
    c=_candidate(ds("RANGKAIAN JALAN",2,["LineString"],[]))
    assert c["candidate_status"]=="not_site_candidate"

def test_no_db_write_contract():
    text=Path("/app/app/services/track_b_smart_site_discovery.py").read_text()
    assert "session.commit" not in text
    assert "session.add" not in text
    assert '"database_writes":False' in text
