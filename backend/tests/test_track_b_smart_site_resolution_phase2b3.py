from pathlib import Path
import json
import pytest

from app.services.track_b import TrackBError
from app.services.track_b_smart_site_resolution import (
    SiteResolutionRequest,
    validate_site_resolution,
    parse_uploaded_boundary_geojson,
)

POLY = {
    "type": "Polygon",
    "coordinates": [[[101.0, 3.0], [101.01, 3.0], [101.01, 3.01], [101.0, 3.01], [101.0, 3.0]]],
}

def test_confirmation_required():
    r = validate_site_resolution(SiteResolutionRequest(
        site_name="Competition Site",
        mode="manual_draw",
        geometry=POLY,
        user_confirmed=False,
    ))
    assert r["status"] == "confirmation_required"
    assert r["ready_for_site_creation"] is False

def test_manual_draw_validated():
    r = validate_site_resolution(SiteResolutionRequest(
        site_name="Competition Site",
        mode="manual_draw",
        geometry=POLY,
        user_confirmed=True,
    ))
    assert r["status"] == "validated"
    assert r["geometry_valid"] is True
    assert r["ready_for_site_creation"] is True
    assert r["database_writes"] is False

def test_uploaded_feature_collection_single_polygon():
    payload = json.dumps({
        "type":"FeatureCollection",
        "features":[{"type":"Feature","properties":{},"geometry":POLY}],
    }).encode()
    r = parse_uploaded_boundary_geojson(
        site_name="Uploaded Site",
        payload=payload,
        source_ref="boundary.geojson",
        user_confirmed=True,
    )
    assert r["mode"] == "uploaded_boundary"
    assert r["ready_for_site_creation"] is True

def test_multiple_polygons_require_explicit_selection():
    payload = json.dumps({
        "type":"FeatureCollection",
        "features":[
            {"type":"Feature","properties":{},"geometry":POLY},
            {"type":"Feature","properties":{},"geometry":POLY},
        ],
    }).encode()
    with pytest.raises(TrackBError):
        parse_uploaded_boundary_geojson(
            site_name="Ambiguous Site",
            payload=payload,
            source_ref="boundary.geojson",
            user_confirmed=True,
        )

def test_no_db_write_contract():
    text = Path("/app/app/services/track_b_smart_site_resolution.py").read_text()
    assert "session.commit" not in text
    assert "session.add" not in text
    assert '"database_writes": False' in text
