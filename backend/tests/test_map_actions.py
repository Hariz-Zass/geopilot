from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.schemas.geometry_reference import GeometryReference, GeometryResolution
from app.schemas.map_action import MapAction, ResolvedMapAction
from app.services.geometry_references import (
    GeometryReferenceNotFoundError,
    GeometryReferenceStaleError,
)
from app.services.map_actions import resolve_map_action


def _hash(char: str = "a") -> str:
    return char * 64


def _site_ref(project_id: uuid.UUID, *, char: str = "a", revision: int = 1) -> GeometryReference:
    return GeometryReference(
        project_id=project_id,
        source_type="site",
        source_id=uuid.uuid4(),
        geometry_hash=_hash(char),
        geometry_revision=revision,
    )


def _resolution(ref: GeometryReference) -> GeometryResolution:
    return GeometryResolution(
        reference=ref,
        geometry={
            "type": "MultiPolygon",
            "coordinates": [[[[101.0, 3.0], [101.1, 3.0], [101.1, 3.1], [101.0, 3.0]]]],
        },
    )


def test_focus_requires_exactly_one_reference() -> None:
    project_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        MapAction(action="focus", geometry_references=[_site_ref(project_id), _site_ref(project_id)])


def test_fit_and_highlight_allow_multiple_references() -> None:
    project_id = uuid.uuid4()
    refs = [_site_ref(project_id, char="a"), _site_ref(project_id, char="b")]
    assert len(MapAction(action="fit", geometry_references=refs).geometry_references) == 2
    assert len(MapAction(action="highlight", geometry_references=refs).geometry_references) == 2


def test_map_action_rejects_duplicate_references() -> None:
    project_id = uuid.uuid4()
    ref = _site_ref(project_id)
    with pytest.raises(ValidationError):
        MapAction(action="highlight", geometry_references=[ref, ref])


def test_map_action_has_no_client_geometry_field() -> None:
    assert "geometry" not in MapAction.model_fields
    assert "geometry" not in MapAction.model_json_schema()["properties"]


def test_resolver_rejects_cross_project_reference_before_delegate() -> None:
    project_id = uuid.uuid4()
    foreign_ref = _site_ref(uuid.uuid4())
    action = MapAction(action="focus", geometry_references=[foreign_ref])
    with patch("app.services.map_actions.resolve_geometry_reference") as delegate:
        with pytest.raises(GeometryReferenceNotFoundError):
            resolve_map_action(Mock(), owner=SimpleNamespace(), project_id=project_id, map_action=action)
    delegate.assert_not_called()


def test_resolver_delegates_every_reference_and_preserves_order() -> None:
    project_id = uuid.uuid4()
    refs = [_site_ref(project_id, char="c"), _site_ref(project_id, char="d")]
    action = MapAction(action="fit", geometry_references=refs, label="Target evidence")
    with patch(
        "app.services.map_actions.resolve_geometry_reference",
        side_effect=[_resolution(refs[0]), _resolution(refs[1])],
    ) as delegate:
        resolved = resolve_map_action(
            Mock(), owner=SimpleNamespace(), project_id=project_id, map_action=action
        )
    assert delegate.call_count == 2
    assert [item.reference for item in resolved.resolved_geometries] == refs
    assert resolved.geometry_authority == "server_resolved"


def test_resolved_map_action_rejects_missing_resolution() -> None:
    project_id = uuid.uuid4()
    ref = _site_ref(project_id)
    action = MapAction(action="focus", geometry_references=[ref])
    with pytest.raises(ValidationError):
        ResolvedMapAction(map_action=action, resolved_geometries=[])


def test_resolver_propagates_stale_reference_fail_closed() -> None:
    project_id = uuid.uuid4()
    ref = _site_ref(project_id)
    action = MapAction(action="focus", geometry_references=[ref])
    with patch(
        "app.services.map_actions.resolve_geometry_reference",
        side_effect=GeometryReferenceStaleError,
    ):
        with pytest.raises(GeometryReferenceStaleError):
            resolve_map_action(Mock(), owner=SimpleNamespace(), project_id=project_id, map_action=action)
