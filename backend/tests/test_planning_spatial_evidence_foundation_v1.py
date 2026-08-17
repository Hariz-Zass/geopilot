import uuid
from types import SimpleNamespace

import pytest

from app.services import planning_spatial_evidence as mod


def polygon_feature():
    return {
        "type": "Feature",
        "id": "zone-1",
        "properties": {"zone": "TEST"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [101.50, 3.00],
                [101.60, 3.00],
                [101.60, 3.10],
                [101.50, 3.10],
                [101.50, 3.00],
            ]],
        },
    }


def request(**overrides):
    data = {
        "layer_name": "Controlled Zoning Test",
        "applicability_role": "zoning",
        "authority": "Test Authority",
        "jurisdiction": "Selangor",
        "source_title": "Controlled Test Dataset",
        "source_kind": "upload",
        "source_name": "zoning.geojson",
        "source_crs": "EPSG:4326",
        "geojson": {
            "type": "FeatureCollection",
            "features": [polygon_feature()],
        },
    }
    data.update(overrides)
    return mod.PlanningSpatialEvidenceImportRequest(**data)


def test_request_requires_controlled_upload_identity():
    with pytest.raises(Exception):
        request(source_name=None)


def test_v1_rejects_non_4326():
    with pytest.raises(Exception):
        request(source_crs="EPSG:32647")


def test_rejects_non_polygon_features():
    payload = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [101.5, 3.0],
            },
            "properties": {},
        }],
    }
    with pytest.raises(mod.PlanningSpatialEvidenceError):
        mod._validated_collection(payload)


def test_import_reuses_existing_gis_services(monkeypatch):
    created = []
    ingested = []

    fake_layer = SimpleNamespace(id=uuid.uuid4())

    def fake_create(session, *, owner, project_id, request):
        created.append(request)
        return fake_layer

    def fake_ingest(session, *, owner, project_id, layer_id, request):
        ingested.append((layer_id, request))
        return [SimpleNamespace(id=uuid.uuid4())]

    monkeypatch.setattr(mod, "create_gis_layer", fake_create)
    monkeypatch.setattr(mod, "ingest_feature_collection", fake_ingest)

    result = mod.import_planning_spatial_evidence(
        SimpleNamespace(),
        owner=SimpleNamespace(id=uuid.uuid4()),
        project_id=uuid.uuid4(),
        request=request(),
    )

    assert result.feature_count == 1
    assert created[0].provenance["applicability_role"] == "zoning"
    assert created[0].provenance["evidence_domain"] == "planning"
    assert created[0].source_crs == "EPSG:4326"
    assert ingested[0][0] == fake_layer.id


def test_allowed_roles_are_exact():
    for role in (
        "zoning",
        "land_use",
        "planning_block",
        "planning_subzone",
    ):
        assert request(applicability_role=role).applicability_role == role
