from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from app.schemas.geometry_reference import GeometryReference
from app.services.geometry_references import (
    GeometryReferenceNotFoundError,
    GeometryReferenceStaleError,
    feature_geometry_reference,
    resolve_geometry_reference,
    site_geometry_reference,
)


def _hash(char: str = "a") -> str:
    return char * 64


def test_site_reference_requires_revision_and_no_layer() -> None:
    site = SimpleNamespace(id=uuid.uuid4(), geometry_hash=_hash(), geometry_revision=3)
    ref = site_geometry_reference(project_id=uuid.uuid4(), site=site)
    assert ref.source_type == "site"
    assert ref.geometry_revision == 3
    assert ref.layer_id is None

    with pytest.raises(ValidationError):
        GeometryReference(
            project_id=uuid.uuid4(),
            source_type="site",
            source_id=uuid.uuid4(),
            geometry_hash=_hash(),
        )


def test_feature_reference_requires_layer_and_no_revision() -> None:
    feature = SimpleNamespace(
        id=uuid.uuid4(), project_id=uuid.uuid4(), layer_id=uuid.uuid4(), geometry_hash=_hash("b")
    )
    ref = feature_geometry_reference(feature=feature)
    assert ref.source_type == "gis_feature"
    assert ref.layer_id == feature.layer_id
    assert ref.geometry_revision is None


def test_reference_rejects_non_sha256_hash() -> None:
    with pytest.raises(ValidationError):
        GeometryReference(
            project_id=uuid.uuid4(),
            source_type="site",
            source_id=uuid.uuid4(),
            geometry_hash="not-a-hash",
            geometry_revision=1,
        )


def test_resolver_rejects_cross_project_reference_before_query() -> None:
    session = Mock()
    owner = SimpleNamespace(id=uuid.uuid4())
    ref = GeometryReference(
        project_id=uuid.uuid4(),
        source_type="site",
        source_id=uuid.uuid4(),
        geometry_hash=_hash(),
        geometry_revision=1,
    )
    with pytest.raises(GeometryReferenceNotFoundError):
        resolve_geometry_reference(
            session, owner=owner, project_id=uuid.uuid4(), reference=ref
        )
    session.execute.assert_not_called()


def test_site_stale_hash_is_rejected() -> None:
    project_id = uuid.uuid4()
    ref = GeometryReference(
        project_id=project_id,
        source_type="site",
        source_id=uuid.uuid4(),
        geometry_hash=_hash("a"),
        geometry_revision=2,
    )
    scope = SimpleNamespace(site=SimpleNamespace(geometry_hash=_hash("c"), geometry_revision=2))
    with patch("app.services.geometry_references.resolve_project_scope"), patch(
        "app.services.geometry_references.resolve_site_scope", return_value=scope
    ):
        with pytest.raises(GeometryReferenceStaleError):
            resolve_geometry_reference(Mock(), owner=SimpleNamespace(), project_id=project_id, reference=ref)


def test_site_resolution_returns_server_geometry() -> None:
    project_id = uuid.uuid4()
    site_id = uuid.uuid4()
    ref = GeometryReference(
        project_id=project_id,
        source_type="site",
        source_id=site_id,
        geometry_hash=_hash("d"),
        geometry_revision=4,
    )
    scope = SimpleNamespace(site=SimpleNamespace(id=site_id, geometry_hash=_hash("d"), geometry_revision=4))
    result = Mock()
    result.scalar_one_or_none.return_value = json.dumps(
        {"type": "MultiPolygon", "coordinates": [[[[101.0, 3.0], [101.1, 3.0], [101.1, 3.1], [101.0, 3.0]]]]}
    )
    session = Mock()
    session.execute.return_value = result
    with patch("app.services.geometry_references.resolve_project_scope"), patch(
        "app.services.geometry_references.resolve_site_scope", return_value=scope
    ):
        resolved = resolve_geometry_reference(
            session, owner=SimpleNamespace(), project_id=project_id, reference=ref
        )
    assert resolved.geometry_authority == "server_resolved"
    assert resolved.reference == ref
    assert resolved.geometry["type"] == "MultiPolygon"


def test_feature_stale_hash_is_rejected() -> None:
    project_id = uuid.uuid4()
    layer_id = uuid.uuid4()
    feature_id = uuid.uuid4()
    ref = GeometryReference(
        project_id=project_id,
        source_type="gis_feature",
        source_id=feature_id,
        layer_id=layer_id,
        geometry_hash=_hash("e"),
    )
    session = Mock()
    session.scalar.side_effect = [SimpleNamespace(is_archived=False, is_active=True), SimpleNamespace(is_archived=False, geometry_hash=_hash("f"))]
    with patch("app.services.geometry_references.resolve_project_scope"):
        with pytest.raises(GeometryReferenceStaleError):
            resolve_geometry_reference(session, owner=SimpleNamespace(), project_id=project_id, reference=ref)
