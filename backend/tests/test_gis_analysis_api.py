from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.db import get_db_session
from app.main import create_app
from app.schemas.gis_analysis import SiteAreaResult
from app.services.gis_analysis import GISAnalysisStateError

P=uuid.UUID('10000000-0000-0000-0000-000000000001')
S=uuid.UUID('20000000-0000-0000-0000-000000000002')
L=uuid.UUID('30000000-0000-0000-0000-000000000003')
F=uuid.UUID('40000000-0000-0000-0000-000000000004')


def client():
    app=create_app()
    app.dependency_overrides[get_current_user]=lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db_session]=lambda: SimpleNamespace()
    return TestClient(app)


def result():
    return SiteAreaResult(project_id=P,site_id=S,site_geometry_hash='a'*64,site_geometry_revision=1,area_sqm=12345,area_hectares=1.2345)


def test_area_endpoint_returns_typed_deterministic_contract():
    with client() as c, patch('app.api.v1.gis_analysis.calculate_site_area',return_value=result()):
        r=c.get(f'/api/v1/projects/{P}/sites/{S}/analysis/gis/area')
    assert r.status_code==200
    b=r.json(); assert b['deterministic'] is True and b['analysis_type']=='site_area'
    assert b['area_sqm']==12345 and b['site_geometry_hash']=='a'*64


def test_scope_state_error_becomes_409_not_invented_result():
    with client() as c, patch('app.api.v1.gis_analysis.calculate_site_area',side_effect=GISAnalysisStateError('layer inactive')):
        r=c.get(f'/api/v1/projects/{P}/sites/{S}/analysis/gis/area')
    assert r.status_code==409
    assert r.json()['error']['code']=='gis_analysis_scope_invalid'


def test_buffer_request_has_bounded_positive_distance():
    with client() as c:
        r=c.post(f'/api/v1/projects/{P}/sites/{S}/analysis/gis/buffer',json={'distance_m':0})
        assert r.status_code==422
        r=c.post(f'/api/v1/projects/{P}/sites/{S}/analysis/gis/buffer',json={'distance_m':100001})
        assert r.status_code==422


def test_nearest_query_contract_bounds_limit_and_distance():
    with client() as c:
        r=c.get(f'/api/v1/projects/{P}/sites/{S}/analysis/gis/layers/{L}/nearest?limit=101')
        assert r.status_code==422
        r=c.get(f'/api/v1/projects/{P}/sites/{S}/analysis/gis/layers/{L}/nearest?max_distance_m=0')
        assert r.status_code==422
