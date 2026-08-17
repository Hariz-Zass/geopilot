from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.schemas.gis_analysis import SiteBufferResult
from app.services.gis_analysis import (
    GISAnalysisResultError,
    GISAnalysisStateError,
    calculate_feature_distance,
    calculate_feature_overlap,
    calculate_site_area,
    calculate_site_buffer,
    find_nearest_features,
)


PROJECT_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
SITE_ID = uuid.UUID("20000000-0000-0000-0000-000000000002")
LAYER_ID = uuid.UUID("30000000-0000-0000-0000-000000000003")
FEATURE_ID = uuid.UUID("40000000-0000-0000-0000-000000000004")
OWNER = SimpleNamespace(id=uuid.UUID("50000000-0000-0000-0000-000000000005"))
SITE = SimpleNamespace(id=SITE_ID, geometry_hash="a" * 64, geometry_revision=3)
SCOPE = SimpleNamespace(site=SITE, project=SimpleNamespace(id=PROJECT_ID))
LAYER = SimpleNamespace(id=LAYER_ID, project_id=PROJECT_ID, is_active=True, is_archived=False)
FEATURE = SimpleNamespace(id=FEATURE_ID, geometry_hash="b" * 64, is_archived=False)


class FakeMappings:
    def __init__(self, *, one=None, all_rows=None):
        self._one = one
        self._all = all_rows or []

    def one_or_none(self):
        return self._one

    def all(self):
        return self._all


class FakeResult:
    def __init__(self, *, one=None, all_rows=None):
        self._mappings = FakeMappings(one=one, all_rows=all_rows)

    def mappings(self):
        return self._mappings


class FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return self.results.pop(0)


def common_patches():
    return (
        patch("app.services.gis_analysis.resolve_analysis_scope", return_value=SCOPE),
        patch("app.services.gis_analysis.get_gis_layer", return_value=LAYER),
        patch("app.services.gis_analysis.get_gis_feature", return_value=FEATURE),
    )


def test_site_area_is_metric_postgis_geography_and_hectares_are_derived():
    session = FakeSession([FakeResult(one={"area_sqm": 25_000.0})])
    with patch("app.services.gis_analysis.resolve_analysis_scope", return_value=SCOPE):
        result = calculate_site_area(session, owner=OWNER, project_id=PROJECT_ID, site_id=SITE_ID)
    assert result.deterministic is True
    assert result.area_sqm == 25_000.0
    assert result.area_hectares == 2.5
    assert result.site_geometry_hash == "a" * 64 and result.site_geometry_revision == 3
    sql = session.calls[0][0]
    assert "ST_Area(geography(s.geometry))" in sql
    assert "s.project_id = :project_id" in sql


def test_distance_uses_exact_feature_identity_and_geography_meters():
    session = FakeSession([FakeResult(one={"distance_m": 812.25})])
    a, b, c = common_patches()
    with a, b, c:
        result = calculate_feature_distance(session, owner=OWNER, project_id=PROJECT_ID, site_id=SITE_ID, layer_id=LAYER_ID, feature_id=FEATURE_ID)
    assert result.distance_m == 812.25
    assert result.feature_geometry_hash == "b" * 64
    sql, params = session.calls[0]
    assert "ST_Distance(geography(s.geometry), geography(f.geometry))" in sql
    assert params["feature_id"] == FEATURE_ID and params["layer_id"] == LAYER_ID


def test_nearest_is_ordered_by_deterministic_distance_then_feature_id_and_can_bound_distance():
    f2 = uuid.UUID("40000000-0000-0000-0000-000000000006")
    rows = [
        {"feature_id": FEATURE_ID, "source_feature_id": "A", "geometry_type": "Point", "geometry_hash": "b"*64, "properties": {"name":"one"}, "distance_m": 10.0},
        {"feature_id": f2, "source_feature_id": "B", "geometry_type": "Point", "geometry_hash": "c"*64, "properties": {}, "distance_m": 20.0},
    ]
    session = FakeSession([FakeResult(all_rows=rows)])
    a, b, _ = common_patches()
    with a, b:
        result = find_nearest_features(session, owner=OWNER, project_id=PROJECT_ID, site_id=SITE_ID, layer_id=LAYER_ID, limit=2, max_distance_m=500)
    assert [x.distance_m for x in result.items] == [10.0,20.0]
    sql, params = session.calls[0]
    assert "ST_DWithin" in sql and "ORDER BY distance_m ASC, f.id ASC" in sql
    assert params["max_distance_m"] == 500 and params["limit"] == 2


def test_overlap_reports_site_and_polygon_feature_percentages_without_ai_math():
    session = FakeSession([FakeResult(one={"intersects": True, "site_area_sqm": 10_000.0, "intersection_area_sqm": 2_500.0, "feature_area_sqm": 5_000.0})])
    a, b, c = common_patches()
    with a, b, c:
        result = calculate_feature_overlap(session, owner=OWNER, project_id=PROJECT_ID, site_id=SITE_ID, layer_id=LAYER_ID, feature_id=FEATURE_ID)
    assert result.intersects is True
    assert result.site_overlap_percent == 25.0
    assert result.feature_overlap_percent == 50.0
    sql = session.calls[0][0]
    assert "ST_Intersection" in sql and "ST_Intersects" in sql
    assert "ST_Area(geography(intersection_geom))" in sql


def test_overlap_for_point_or_line_has_no_feature_area_percentage():
    session = FakeSession([FakeResult(one={"intersects": True, "site_area_sqm": 10_000.0, "intersection_area_sqm": 0.0, "feature_area_sqm": None})])
    a, b, c = common_patches()
    with a, b, c:
        result = calculate_feature_overlap(session, owner=OWNER, project_id=PROJECT_ID, site_id=SITE_ID, layer_id=LAYER_ID, feature_id=FEATURE_ID)
    assert result.intersection_area_sqm == 0.0
    assert result.feature_area_sqm is None and result.feature_overlap_percent is None


def test_buffer_returns_only_server_derived_ephemeral_geometry():
    session = FakeSession([FakeResult(one={"buffer_area_sqm": 99_000.0, "geometry_geojson": '{"type":"Polygon","coordinates":[]}'})])
    with patch("app.services.gis_analysis.resolve_analysis_scope", return_value=SCOPE):
        result = calculate_site_buffer(session, owner=OWNER, project_id=PROJECT_ID, site_id=SITE_ID, distance_m=100.0)
    assert isinstance(result, SiteBufferResult)
    assert result.geometry_role == "ephemeral_server_derived"
    assert result.distance_m == 100.0 and result.buffer_area_sqm == 99_000.0
    sql = session.calls[0][0]
    assert "ST_Buffer(geography(s.geometry), :distance_m)" in sql
    assert "ST_AsGeoJSON" in sql


def test_inactive_or_archived_layer_is_rejected_before_query():
    bad = SimpleNamespace(id=LAYER_ID, project_id=PROJECT_ID, is_active=False, is_archived=False)
    session = FakeSession([])
    with patch("app.services.gis_analysis.resolve_analysis_scope", return_value=SCOPE), patch("app.services.gis_analysis.get_gis_layer", return_value=bad):
        with pytest.raises(GISAnalysisStateError):
            find_nearest_features(session, owner=OWNER, project_id=PROJECT_ID, site_id=SITE_ID, layer_id=LAYER_ID)
    assert session.calls == []


def test_archived_feature_is_rejected_before_query():
    bad_feature = SimpleNamespace(id=FEATURE_ID, geometry_hash="b"*64, is_archived=True)
    session = FakeSession([])
    with patch("app.services.gis_analysis.resolve_analysis_scope", return_value=SCOPE), patch("app.services.gis_analysis.get_gis_layer", return_value=LAYER), patch("app.services.gis_analysis.get_gis_feature", return_value=bad_feature):
        with pytest.raises(GISAnalysisStateError):
            calculate_feature_distance(session, owner=OWNER, project_id=PROJECT_ID, site_id=SITE_ID, layer_id=LAYER_ID, feature_id=FEATURE_ID)
    assert session.calls == []


def test_missing_postgis_row_fails_closed():
    session = FakeSession([FakeResult(one=None)])
    with patch("app.services.gis_analysis.resolve_analysis_scope", return_value=SCOPE):
        with pytest.raises(GISAnalysisResultError):
            calculate_site_area(session, owner=OWNER, project_id=PROJECT_ID, site_id=SITE_ID)


def test_invalid_negative_measurement_fails_closed():
    session = FakeSession([FakeResult(one={"area_sqm": -1})])
    with patch("app.services.gis_analysis.resolve_analysis_scope", return_value=SCOPE):
        with pytest.raises(GISAnalysisResultError):
            calculate_site_area(session, owner=OWNER, project_id=PROJECT_ID, site_id=SITE_ID)
