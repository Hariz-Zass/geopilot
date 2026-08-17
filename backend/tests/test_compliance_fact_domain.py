from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db_session
from app.db.base import Base
from app.main import create_app
from app.schemas.gis_analysis import SiteAreaResult


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def register_spatial_passthrough(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        dbapi_connection.create_function("ST_GeomFromEWKT", 1, lambda value: value)
        dbapi_connection.create_function("ST_AsEWKT", 1, lambda value: value)

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def client(session_factory):
    app = create_app()

    def override():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    with TestClient(app) as c:
        yield c


def h(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email="facts@example.com"):
    password = "correct horse battery staple"
    client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": "Fact Owner"})
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]


def create_project_site(client, token, name="Facts Project"):
    pid = client.post("/api/v1/projects", headers=h(token), json={"name": name}).json()["id"]
    geom = {
        "type": "Polygon",
        "coordinates": [[[101.0, 3.0], [101.01, 3.0], [101.01, 3.01], [101.0, 3.01], [101.0, 3.0]]],
    }
    site = client.post(f"/api/v1/projects/{pid}/sites", headers=h(token), json={"name": "Target", "geometry": geom}).json()
    return pid, site


def user_fact_payload(value="30"):
    return {
        "metric_key": "proposal.open_space_percent",
        "label": "Proposed open-space percentage",
        "value_type": "numeric",
        "unit": "percent",
        "numeric_value": value,
        "source_description": "Owner-supplied proposal schedule dated 2026-08-14.",
    }


def test_create_user_supplied_fact_is_explicit_owner_assertion(client):
    token = login(client)
    pid, site = create_project_site(client, token)
    r = client.post(f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts/user-supplied", headers=h(token), json=user_fact_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_kind"] == "user_supplied"
    assert body["source_method"] == "owner_assertion_v1"
    assert body["source_details"]["independently_measured"] is False
    assert str(body["numeric_value"]).startswith("30")
    assert body["site_geometry_hash"] == site["geometry_hash"]
    assert body["site_geometry_revision"] == site["geometry_revision"]


def test_user_fact_payload_shape_is_fail_closed(client):
    token = login(client)
    pid, site = create_project_site(client, token)
    payload = user_fact_payload()
    payload["text_value"] = "thirty"
    r = client.post(f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts/user-supplied", headers=h(token), json=payload)
    assert r.status_code == 422


def test_identical_user_fact_provenance_is_rejected(client):
    token = login(client)
    pid, site = create_project_site(client, token)
    url = f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts/user-supplied"
    assert client.post(url, headers=h(token), json=user_fact_payload()).status_code == 201
    r = client.post(url, headers=h(token), json=user_fact_payload())
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "compliance_fact_state_invalid"


def test_user_fact_resolve_surfaces_limitation_not_compliance_conclusion(client):
    token = login(client)
    pid, site = create_project_site(client, token)
    item = client.post(f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts/user-supplied", headers=h(token), json=user_fact_payload()).json()
    r = client.post(f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts/{item['id']}/resolve", headers=h(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "validated"
    assert any("owner-supplied assertion" in x for x in body["limitations"])
    assert any("not a compliance finding" in x for x in body["limitations"])


def test_archived_fact_cannot_resolve_and_is_hidden_by_default(client):
    token = login(client)
    pid, site = create_project_site(client, token)
    base = f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts"
    item = client.post(f"{base}/user-supplied", headers=h(token), json=user_fact_payload()).json()
    archived = client.patch(f"{base}/{item['id']}", headers=h(token), json={"is_archived": True})
    assert archived.status_code == 200 and archived.json()["is_archived"] is True
    assert client.get(base, headers=h(token)).json() == []
    assert len(client.get(f"{base}?include_archived=true", headers=h(token)).json()) == 1
    assert client.post(f"{base}/{item['id']}/resolve", headers=h(token)).status_code == 409


def test_fact_becomes_stale_when_site_geometry_changes(client):
    token = login(client)
    pid, site = create_project_site(client, token)
    base = f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts"
    item = client.post(f"{base}/user-supplied", headers=h(token), json=user_fact_payload()).json()
    changed = {
        "type": "Polygon",
        "coordinates": [[[101.0, 3.0], [101.02, 3.0], [101.02, 3.01], [101.0, 3.01], [101.0, 3.0]]],
    }
    patch = client.patch(f"/api/v1/projects/{pid}/sites/{site['id']}", headers=h(token), json={"geometry": changed})
    assert patch.status_code == 200
    r = client.post(f"{base}/{item['id']}/resolve", headers=h(token))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "compliance_fact_source_stale"


def test_cross_owner_fact_is_missing_equivalent(client):
    a = login(client, "facts-a@example.com")
    pid, site = create_project_site(client, a, "A")
    item = client.post(f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts/user-supplied", headers=h(a), json=user_fact_payload()).json()
    b = login(client, "facts-b@example.com")
    r = client.get(f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts/{item['id']}", headers=h(b))
    assert r.status_code == 404


def test_same_owner_cross_project_site_substitution_fails(client):
    token = login(client)
    p1, site1 = create_project_site(client, token, "P1")
    p2, _site2 = create_project_site(client, token, "P2")
    item = client.post(f"/api/v1/projects/{p1}/sites/{site1['id']}/compliance-facts/user-supplied", headers=h(token), json=user_fact_payload()).json()
    r = client.get(f"/api/v1/projects/{p2}/sites/{site1['id']}/compliance-facts/{item['id']}", headers=h(token))
    assert r.status_code in {404, 409}


def test_gis_site_area_value_is_server_derived_not_client_supplied(client, monkeypatch):
    token = login(client)
    pid, site = create_project_site(client, token)

    def fake_area(session, *, owner, project_id, site_id):
        return SiteAreaResult(
            project_id=project_id,
            site_id=site_id,
            site_geometry_hash=site["geometry_hash"],
            site_geometry_revision=site["geometry_revision"],
            area_sqm=12345.0,
            area_hectares=1.2345,
        )

    monkeypatch.setattr("app.services.compliance_facts.calculate_site_area", fake_area)
    payload = {
        "analysis_type": "site_area",
        "metric_key": "site.area_hectares",
        "label": "Measured site area",
        "output_field": "area_hectares",
    }
    r = client.post(f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts/from-gis", headers=h(token), json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_kind"] == "gis_analysis"
    assert body["source_method"] == "postgis-geography-v1"
    assert body["unit"] == "hectares"
    assert Decimal(body["numeric_value"]) == Decimal("1.23450000")
    assert body["source_details"]["deterministic"] is True


def test_gis_request_does_not_accept_client_numeric_value(client):
    token = login(client)
    pid, site = create_project_site(client, token)
    payload = {
        "analysis_type": "site_area",
        "metric_key": "site.area_hectares",
        "label": "Fake area",
        "output_field": "area_hectares",
        "numeric_value": 999,
    }
    r = client.post(f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts/from-gis", headers=h(token), json=payload)
    assert r.status_code == 422


def test_feature_distance_fact_preserves_exact_feature_lineage_and_detects_archive(client, monkeypatch):
    from app.schemas.gis_analysis import FeatureDistanceResult

    token = login(client, "facts-feature@example.com")
    pid, site = create_project_site(client, token, "Feature Fact Project")
    layer = client.post(
        f"/api/v1/projects/{pid}/gis-layers",
        headers=h(token),
        json={
            "name": "Roads",
            "source_kind": "upload",
            "source_name": "roads.geojson",
            "source_crs": "EPSG:4326",
            "geometry_type": "Point",
            "provenance": {"owner_upload": True},
        },
    ).json()
    feature = client.post(
        f"/api/v1/projects/{pid}/gis-layers/{layer['id']}/features",
        headers=h(token),
        json={"source_feature_id": "road-node-1", "geometry": {"type": "Point", "coordinates": [101.03, 3.02]}, "properties": {}},
    ).json()

    def fake_distance(session, *, owner, project_id, site_id, layer_id, feature_id):
        return FeatureDistanceResult(
            project_id=project_id,
            site_id=site_id,
            site_geometry_hash=site["geometry_hash"],
            site_geometry_revision=site["geometry_revision"],
            layer_id=layer_id,
            feature_id=feature_id,
            feature_geometry_hash=feature["geometry_hash"],
            distance_m=425.75,
        )

    monkeypatch.setattr("app.services.compliance_facts.calculate_feature_distance", fake_distance)
    base = f"/api/v1/projects/{pid}/sites/{site['id']}/compliance-facts"
    r = client.post(
        f"{base}/from-gis",
        headers=h(token),
        json={
            "analysis_type": "feature_distance",
            "metric_key": "site.distance_to_road_m",
            "label": "Distance to road evidence",
            "output_field": "distance_m",
            "layer_id": layer["id"],
            "feature_id": feature["id"],
        },
    )
    assert r.status_code == 201, r.text
    fact = r.json()
    assert fact["source_gis_layer_id"] == layer["id"]
    assert fact["source_gis_feature_id"] == feature["id"]
    assert fact["source_feature_geometry_hash"] == feature["geometry_hash"]
    assert Decimal(fact["numeric_value"]) == Decimal("425.75000000")
    assert client.post(f"{base}/{fact['id']}/resolve", headers=h(token)).status_code == 200

    archived = client.patch(
        f"/api/v1/projects/{pid}/gis-layers/{layer['id']}/features/{feature['id']}/archive",
        headers=h(token),
    )
    assert archived.status_code == 200
    stale = client.post(f"{base}/{fact['id']}/resolve", headers=h(token))
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "compliance_fact_source_stale"
