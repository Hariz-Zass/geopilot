from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.gis_feature import GISFeature
from app.models.gis_layer import GISLayer
from app.models.user import User
from app.schemas.gis_analysis import (
    FeatureDistanceResult,
    FeatureOverlapResult,
    NearestFeatureItem,
    NearestFeaturesResult,
    SiteAreaResult,
    SiteBufferResult,
)
from app.services.gis_features import GISFeatureNotFoundError, get_gis_feature
from app.services.gis_layers import get_gis_layer
from app.services.isolation import SiteScope, SiteState, resolve_analysis_scope


class GISAnalysisStateError(Exception):
    """Scoped evidence exists but is not eligible for deterministic analysis."""


class GISAnalysisResultError(Exception):
    """PostGIS returned a missing, malformed, or impossible deterministic result."""


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    scope: SiteScope
    layer: GISLayer | None = None
    feature: GISFeature | None = None


def _analysis_scope(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> SiteScope:
    return resolve_analysis_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )


def _analysis_layer(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    layer_id: uuid.UUID,
) -> GISLayer:
    layer = get_gis_layer(
        session, owner=owner, project_id=project_id, layer_id=layer_id
    )
    if layer.is_archived or not layer.is_active:
        raise GISAnalysisStateError(
            "deterministic GIS analysis requires an active, non-archived GIS layer"
        )
    return layer


def _analysis_feature(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    layer_id: uuid.UUID,
    feature_id: uuid.UUID,
) -> GISFeature:
    feature = get_gis_feature(
        session,
        owner=owner,
        project_id=project_id,
        layer_id=layer_id,
        feature_id=feature_id,
    )
    if feature.is_archived:
        raise GISAnalysisStateError(
            "deterministic GIS analysis cannot use an archived GIS feature"
        )
    return feature


def _mapping_one(session: Session, sql: str, params: dict[str, Any]) -> dict[str, Any]:
    row = session.execute(text(sql), params).mappings().one_or_none()
    if row is None:
        raise GISAnalysisResultError("deterministic spatial query returned no row")
    return dict(row)


def calculate_site_area(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> SiteAreaResult:
    scope = _analysis_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )
    active_clause = (
        "AND s.is_active IS TRUE"
        if site_state is SiteState.ACTIVE
        else ""
    )
    row = _mapping_one(
        session,
        f"""
        SELECT ST_Area(geography(s.geometry)) AS area_sqm
        FROM sites AS s
        WHERE s.id = :site_id
          AND s.project_id = :project_id
          {active_clause}
          AND s.is_archived IS FALSE
        """,
        {"site_id": site_id, "project_id": project_id},
    )
    area_sqm = float(row["area_sqm"])
    if area_sqm < 0:
        raise GISAnalysisResultError("site area cannot be negative")
    return SiteAreaResult(
        project_id=project_id,
        site_id=site_id,
        site_geometry_hash=scope.site.geometry_hash,
        site_geometry_revision=scope.site.geometry_revision,
        area_sqm=area_sqm,
        area_hectares=area_sqm / 10_000.0,
    )


def calculate_feature_distance(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    layer_id: uuid.UUID,
    feature_id: uuid.UUID,
) -> FeatureDistanceResult:
    scope = _analysis_scope(
        session, owner=owner, project_id=project_id, site_id=site_id
    )
    _analysis_layer(
        session, owner=owner, project_id=project_id, layer_id=layer_id
    )
    feature = _analysis_feature(
        session,
        owner=owner,
        project_id=project_id,
        layer_id=layer_id,
        feature_id=feature_id,
    )
    row = _mapping_one(
        session,
        """
        SELECT ST_Distance(geography(s.geometry), geography(f.geometry)) AS distance_m
        FROM sites AS s
        JOIN gis_features AS f
          ON f.id = :feature_id
         AND f.project_id = s.project_id
         AND f.layer_id = :layer_id
         AND f.is_archived IS FALSE
        WHERE s.id = :site_id
          AND s.project_id = :project_id
          AND s.is_active IS TRUE
          AND s.is_archived IS FALSE
        """,
        {
            "site_id": site_id,
            "project_id": project_id,
            "layer_id": layer_id,
            "feature_id": feature_id,
        },
    )
    distance_m = float(row["distance_m"])
    if distance_m < 0:
        raise GISAnalysisResultError("feature distance cannot be negative")
    return FeatureDistanceResult(
        project_id=project_id,
        site_id=site_id,
        site_geometry_hash=scope.site.geometry_hash,
        site_geometry_revision=scope.site.geometry_revision,
        layer_id=layer_id,
        feature_id=feature_id,
        feature_geometry_hash=feature.geometry_hash,
        distance_m=distance_m,
    )


def find_nearest_features(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    layer_id: uuid.UUID,
    limit: int = 5,
    max_distance_m: float | None = None,
) -> NearestFeaturesResult:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    if max_distance_m is not None and max_distance_m <= 0:
        raise ValueError("max_distance_m must be positive")

    scope = _analysis_scope(
        session, owner=owner, project_id=project_id, site_id=site_id
    )
    _analysis_layer(
        session, owner=owner, project_id=project_id, layer_id=layer_id
    )

    distance_filter = ""
    params: dict[str, Any] = {
        "site_id": site_id,
        "project_id": project_id,
        "layer_id": layer_id,
        "limit": limit,
    }
    if max_distance_m is not None:
        distance_filter = (
            "AND ST_DWithin(geography(s.geometry), geography(f.geometry), :max_distance_m)"
        )
        params["max_distance_m"] = max_distance_m

    rows = session.execute(
        text(
            f"""
            SELECT
                f.id AS feature_id,
                f.source_feature_id,
                f.geometry_type,
                f.geometry_hash,
                f.properties,
                ST_Distance(geography(s.geometry), geography(f.geometry)) AS distance_m
            FROM sites AS s
            JOIN gis_features AS f
              ON f.project_id = s.project_id
             AND f.layer_id = :layer_id
             AND f.is_archived IS FALSE
            WHERE s.id = :site_id
              AND s.project_id = :project_id
              AND s.is_active IS TRUE
              AND s.is_archived IS FALSE
              {distance_filter}
            ORDER BY distance_m ASC, f.id ASC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    items = [
        NearestFeatureItem(
            feature_id=row["feature_id"],
            source_feature_id=row["source_feature_id"],
            geometry_type=row["geometry_type"],
            geometry_hash=row["geometry_hash"],
            properties=row["properties"] or {},
            distance_m=float(row["distance_m"]),
        )
        for row in rows
    ]
    return NearestFeaturesResult(
        project_id=project_id,
        site_id=site_id,
        site_geometry_hash=scope.site.geometry_hash,
        site_geometry_revision=scope.site.geometry_revision,
        layer_id=layer_id,
        max_distance_m=max_distance_m,
        items=items,
    )


def calculate_feature_overlap(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    layer_id: uuid.UUID,
    feature_id: uuid.UUID,
) -> FeatureOverlapResult:
    scope = _analysis_scope(
        session, owner=owner, project_id=project_id, site_id=site_id
    )
    _analysis_layer(
        session, owner=owner, project_id=project_id, layer_id=layer_id
    )
    feature = _analysis_feature(
        session,
        owner=owner,
        project_id=project_id,
        layer_id=layer_id,
        feature_id=feature_id,
    )

    row = _mapping_one(
        session,
        """
        WITH spatial AS (
            SELECT
                s.geometry AS site_geom,
                f.geometry AS feature_geom,
                ST_Intersection(s.geometry, f.geometry) AS intersection_geom
            FROM sites AS s
            JOIN gis_features AS f
              ON f.id = :feature_id
             AND f.project_id = s.project_id
             AND f.layer_id = :layer_id
             AND f.is_archived IS FALSE
            WHERE s.id = :site_id
              AND s.project_id = :project_id
              AND s.is_active IS TRUE
              AND s.is_archived IS FALSE
        )
        SELECT
            ST_Intersects(site_geom, feature_geom) AS intersects,
            ST_Area(geography(site_geom)) AS site_area_sqm,
            CASE
              WHEN ST_Dimension(intersection_geom) = 2
              THEN ST_Area(geography(intersection_geom))
              ELSE 0.0
            END AS intersection_area_sqm,
            CASE
              WHEN ST_Dimension(feature_geom) = 2
              THEN ST_Area(geography(feature_geom))
              ELSE NULL
            END AS feature_area_sqm
        FROM spatial
        """,
        {
            "site_id": site_id,
            "project_id": project_id,
            "layer_id": layer_id,
            "feature_id": feature_id,
        },
    )
    site_area = float(row["site_area_sqm"])
    intersection_area = float(row["intersection_area_sqm"])
    feature_area = (
        None if row["feature_area_sqm"] is None else float(row["feature_area_sqm"])
    )
    if site_area <= 0 or intersection_area < 0 or (feature_area is not None and feature_area < 0):
        raise GISAnalysisResultError("invalid overlap measurement returned by PostGIS")

    site_pct = min(100.0, max(0.0, intersection_area / site_area * 100.0))
    feature_pct = None
    if feature_area is not None and feature_area > 0:
        feature_pct = min(100.0, max(0.0, intersection_area / feature_area * 100.0))

    return FeatureOverlapResult(
        project_id=project_id,
        site_id=site_id,
        site_geometry_hash=scope.site.geometry_hash,
        site_geometry_revision=scope.site.geometry_revision,
        layer_id=layer_id,
        feature_id=feature_id,
        feature_geometry_hash=feature.geometry_hash,
        intersects=bool(row["intersects"]),
        intersection_area_sqm=intersection_area,
        site_area_sqm=site_area,
        site_overlap_percent=site_pct,
        feature_area_sqm=feature_area,
        feature_overlap_percent=feature_pct,
    )


def calculate_site_buffer(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    distance_m: float,
) -> SiteBufferResult:
    if distance_m <= 0 or distance_m > 100_000:
        raise ValueError("distance_m must be greater than 0 and at most 100000")
    scope = _analysis_scope(
        session, owner=owner, project_id=project_id, site_id=site_id
    )
    row = _mapping_one(
        session,
        """
        SELECT
            ST_Area(ST_Buffer(geography(s.geometry), :distance_m)) AS buffer_area_sqm,
            ST_AsGeoJSON(geometry(ST_Buffer(geography(s.geometry), :distance_m))) AS geometry_geojson
        FROM sites AS s
        WHERE s.id = :site_id
          AND s.project_id = :project_id
          AND s.is_active IS TRUE
          AND s.is_archived IS FALSE
        """,
        {"site_id": site_id, "project_id": project_id, "distance_m": distance_m},
    )
    area = float(row["buffer_area_sqm"])
    raw_geometry = row["geometry_geojson"]
    geometry = json.loads(raw_geometry) if isinstance(raw_geometry, str) else raw_geometry
    if area < 0 or not isinstance(geometry, dict):
        raise GISAnalysisResultError("invalid buffer result returned by PostGIS")
    return SiteBufferResult(
        project_id=project_id,
        site_id=site_id,
        site_geometry_hash=scope.site.geometry_hash,
        site_geometry_revision=scope.site.geometry_revision,
        distance_m=distance_m,
        buffer_area_sqm=area,
        geometry=geometry,
    )
