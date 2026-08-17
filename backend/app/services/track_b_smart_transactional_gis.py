from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gis_feature import GISFeature
from app.models.gis_layer import GISLayer
from app.models.user import User
from app.schemas.gis_feature import (
    GISFeatureCreateRequest,
    GISFeatureInput,
    geometry_digest,
    geometry_to_ewkt,
)
from app.schemas.gis_layer import GISLayerCreateRequest
from app.services.isolation import (
    ProjectScopeNotFoundError,
    ProjectState,
    ScopeStateError,
    resolve_project_scope,
)
from app.services.gis_layers import GISLayerProjectNotFoundError, GISLayerStateError
from app.services.gis_features import GISFeatureStateError

# SMART_ORGANIZER_PHASE2C3A_TRANSACTIONAL_GIS


@dataclass(frozen=True)
class TransactionalLayerResult:
    layer: GISLayer
    created: bool
    duplicate: bool


@dataclass(frozen=True)
class TransactionalFeatureBatchResult:
    features: list[GISFeature]
    created_count: int
    duplicate_count: int


def _active_project(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
):
    try:
        return resolve_project_scope(
            session,
            owner=owner,
            project_id=project_id,
            state=ProjectState.ACTIVE,
        ).project
    except ProjectScopeNotFoundError as exc:
        raise GISLayerProjectNotFoundError from exc
    except ScopeStateError as exc:
        raise GISLayerStateError(str(exc)) from exc


def _role(request: GISLayerCreateRequest) -> str | None:
    provenance = request.provenance or {}
    value = provenance.get("applicability_role")
    if not isinstance(value, str):
        return None
    value = value.strip().casefold()
    return value or None


def create_gis_layer_uncommitted(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    request: GISLayerCreateRequest,
) -> TransactionalLayerResult:
    """
    Transaction-aware GISLayer creation.

    Never commits. Duplicate identity is:
      project_id + source_checksum_sha256 + provenance.applicability_role
    when a checksum is available.
    """
    project = _active_project(
        session,
        owner=owner,
        project_id=project_id,
    )

    role = _role(request)

    if request.source_checksum_sha256:
        existing_layers = list(
            session.scalars(
                select(GISLayer).where(
                    GISLayer.project_id == project.id,
                    GISLayer.source_checksum_sha256 == request.source_checksum_sha256,
                    GISLayer.is_archived.is_(False),
                )
            )
        )
        for existing in existing_layers:
            existing_role = None
            if isinstance(existing.provenance, dict):
                raw = existing.provenance.get("applicability_role")
                if isinstance(raw, str):
                    existing_role = raw.strip().casefold() or None
            if existing_role == role:
                return TransactionalLayerResult(
                    layer=existing,
                    created=False,
                    duplicate=True,
                )

    layer = GISLayer(
        project_id=project.id,
        **request.model_dump(),
    )
    session.add(layer)
    session.flush()

    return TransactionalLayerResult(
        layer=layer,
        created=True,
        duplicate=False,
    )


def _feature_key(
    *,
    source_feature_id: str | None,
    geometry_hash: str,
) -> tuple[str, str]:
    if source_feature_id:
        return ("source_feature_id", source_feature_id)
    return ("geometry_hash", geometry_hash)


def _build_feature(
    layer: GISLayer,
    request: GISFeatureCreateRequest,
) -> GISFeature:
    feature_type = request.geometry.type
    declared = layer.geometry_type

    if declared in {None, "Unknown"}:
        layer.geometry_type = feature_type
    elif declared != feature_type and declared != "Mixed":
        raise GISFeatureStateError(
            f"feature geometry type {feature_type} does not match layer geometry_type {declared}"
        )

    return GISFeature(
        project_id=layer.project_id,
        layer_id=layer.id,
        source_feature_id=request.source_feature_id,
        geometry=geometry_to_ewkt(request.geometry),
        geometry_type=feature_type,
        geometry_hash=geometry_digest(request.geometry),
        properties=request.properties,
    )


def ingest_features_uncommitted(
    session: Session,
    *,
    layer: GISLayer,
    features: Iterable[GISFeatureInput],
) -> TransactionalFeatureBatchResult:
    """
    Transaction-aware feature ingestion.

    Never commits or rolls back. Caller owns transaction.
    Existing duplicates are skipped deterministically.
    """
    if layer.is_archived or not layer.is_active:
        raise GISFeatureStateError(
            "GIS features may only be ingested into an active, non-archived GIS layer"
        )

    existing = list(
        session.scalars(
            select(GISFeature).where(
                GISFeature.project_id == layer.project_id,
                GISFeature.layer_id == layer.id,
                GISFeature.is_archived.is_(False),
            )
        )
    )

    seen: set[tuple[str, str]] = set()
    for item in existing:
        seen.add(
            _feature_key(
                source_feature_id=item.source_feature_id,
                geometry_hash=item.geometry_hash,
            )
        )

    built: list[GISFeature] = []
    duplicate_count = 0

    for item in features:
        source_id = None if item.id is None else str(item.id).strip() or None
        request = GISFeatureCreateRequest(
            source_feature_id=source_id,
            geometry=item.geometry,
            properties=item.properties,
        )
        digest = geometry_digest(request.geometry)
        key = _feature_key(
            source_feature_id=request.source_feature_id,
            geometry_hash=digest,
        )

        if key in seen:
            duplicate_count += 1
            continue

        feature = _build_feature(layer, request)
        built.append(feature)
        seen.add(key)

    if built:
        session.add_all(built)
        session.flush()

    return TransactionalFeatureBatchResult(
        features=built,
        created_count=len(built),
        duplicate_count=duplicate_count,
    )
