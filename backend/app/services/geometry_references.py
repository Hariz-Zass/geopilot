from __future__ import annotations

import json
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.gis_feature import GISFeature
from app.models.gis_layer import GISLayer
from app.models.user import User
from app.schemas.geometry_reference import GeometryReference, GeometryResolution
from app.services.isolation import (
    ProjectState,
    SiteState,
    resolve_project_scope,
    resolve_site_scope,
)


class GeometryReferenceNotFoundError(Exception):
    """Referenced geometry does not exist inside the authorized scope."""


class GeometryReferenceStateError(Exception):
    """Referenced source exists but is archived/inactive and cannot resolve."""


class GeometryReferenceStaleError(Exception):
    """Reference identity no longer matches the current authoritative geometry."""


class GeometryResolutionError(Exception):
    """The authoritative geometry could not be serialized safely."""


def site_geometry_reference(*, project_id: uuid.UUID, site) -> GeometryReference:
    return GeometryReference(
        project_id=project_id,
        source_type="site",
        source_id=site.id,
        geometry_hash=site.geometry_hash,
        geometry_revision=site.geometry_revision,
    )


def feature_geometry_reference(*, feature: GISFeature) -> GeometryReference:
    return GeometryReference(
        project_id=feature.project_id,
        source_type="gis_feature",
        source_id=feature.id,
        layer_id=feature.layer_id,
        geometry_hash=feature.geometry_hash,
    )


def _read_geojson(
    session: Session,
    *,
    table: str,
    source_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict:
    if table not in {"sites", "gis_features"}:
        raise GeometryResolutionError("unsupported geometry source table")
    value = session.execute(
        text(
            f"""
            SELECT ST_AsGeoJSON(geometry)
            FROM {table}
            WHERE id = :source_id AND project_id = :project_id
            """
        ),
        {"source_id": source_id, "project_id": project_id},
    ).scalar_one_or_none()
    if value is None:
        raise GeometryReferenceNotFoundError
    try:
        geometry = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError) as exc:
        raise GeometryResolutionError("authoritative geometry is not valid GeoJSON") from exc
    if not isinstance(geometry, dict):
        raise GeometryResolutionError("authoritative geometry is not a GeoJSON object")
    return geometry


def resolve_geometry_reference(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    reference: GeometryReference,
) -> GeometryResolution:
    # Do not permit a valid reference to be replayed beneath another project
    # path, even if both projects belong to the same authenticated user.
    if reference.project_id != project_id:
        raise GeometryReferenceNotFoundError

    resolve_project_scope(
        session,
        owner=owner,
        project_id=project_id,
        state=ProjectState.ACTIVE,
    )

    if reference.source_type == "site":
        scope = resolve_site_scope(
            session,
            owner=owner,
            project_id=project_id,
            site_id=reference.source_id,
            project_state=ProjectState.ACTIVE,
            site_state=SiteState.AVAILABLE,
        )
        site = scope.site
        if (
            site.geometry_hash != reference.geometry_hash
            or site.geometry_revision != reference.geometry_revision
        ):
            raise GeometryReferenceStaleError
        geometry = _read_geojson(
            session,
            table="sites",
            source_id=site.id,
            project_id=project_id,
        )
        return GeometryResolution(reference=reference, geometry=geometry)

    assert reference.layer_id is not None
    layer = session.scalar(
        select(GISLayer).where(
            GISLayer.id == reference.layer_id,
            GISLayer.project_id == project_id,
        )
    )
    if layer is None:
        raise GeometryReferenceNotFoundError
    if layer.is_archived or not layer.is_active:
        raise GeometryReferenceStateError("GIS layer is not available for geometry resolution")

    feature = session.scalar(
        select(GISFeature).where(
            GISFeature.id == reference.source_id,
            GISFeature.project_id == project_id,
            GISFeature.layer_id == reference.layer_id,
        )
    )
    if feature is None:
        raise GeometryReferenceNotFoundError
    if feature.is_archived:
        raise GeometryReferenceStateError("GIS feature is archived")
    if feature.geometry_hash != reference.geometry_hash:
        raise GeometryReferenceStaleError

    geometry = _read_geojson(
        session,
        table="gis_features",
        source_id=feature.id,
        project_id=project_id,
    )
    return GeometryResolution(reference=reference, geometry=geometry)
