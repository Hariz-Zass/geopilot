from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.gis_layer import GISLayer
from app.models.user import User
from app.services.gis_layers import list_gis_layers
from app.services.isolation import SiteState, resolve_analysis_scope


APPLICABILITY_ROLES = {
    "planning_block",
    "planning_subzone",
    "zoning",
    "land_use",
}


@dataclass(frozen=True, slots=True)
class SiteApplicabilityMatch:
    project_id: uuid.UUID
    site_id: uuid.UUID
    site_geometry_hash: str
    site_geometry_revision: int

    layer_id: uuid.UUID
    layer_name: str
    applicability_role: str
    layer_provenance: dict[str, Any]

    feature_id: uuid.UUID
    source_feature_id: str | None
    feature_geometry_hash: str
    properties: dict[str, Any]

    intersection_area_sqm: float
    site_area_sqm: float
    site_overlap_percent: float


def _layer_role(layer: GISLayer) -> str | None:
    provenance = layer.provenance or {}
    value = provenance.get("applicability_role")

    if not isinstance(value, str):
        return None

    role = value.strip().casefold()
    return role or None


def _eligible_layers(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
) -> list[GISLayer]:
    layers = list_gis_layers(
        session,
        owner=owner,
        project_id=project_id,
        include_archived=False,
    )

    eligible: list[GISLayer] = []

    for layer in layers:
        if not layer.is_active or layer.is_archived:
            continue

        role = _layer_role(layer)
        if role not in APPLICABILITY_ROLES:
            continue

        if layer.geometry_type not in {
            "Polygon",
            "MultiPolygon",
            "Mixed",
        }:
            continue

        eligible.append(layer)

    return eligible


def resolve_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> tuple[list[SiteApplicabilityMatch], list[str]]:
    """
    Resolve all active planning applicability polygons that overlap the
    server-owned active Site.

    Layers are selected only when their provenance explicitly declares
    `applicability_role`, avoiding inference from arbitrary layer names.
    """
    scope = resolve_analysis_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )

    layers = _eligible_layers(
        session,
        owner=owner,
        project_id=project_id,
    )

    if not layers:
        return [], [
            (
                "No active polygon GIS layer is classified with "
                "provenance.applicability_role as planning_block, "
                "planning_subzone, zoning, or land_use."
            )
        ]

    layer_by_id = {
        layer.id: layer
        for layer in layers
    }

    layer_ids = [
        str(layer.id)
        for layer in layers
    ]

    sql = text(
        """
        WITH site_scope AS (
            SELECT
                s.id,
                s.project_id,
                s.geometry,
                ST_Area(geography(s.geometry)) AS site_area_sqm
            FROM sites AS s
            WHERE s.id = :site_id
              AND s.project_id = :project_id
              AND (
                  CAST(:require_active AS boolean) IS FALSE
                  OR s.is_active IS TRUE
              )
              AND s.is_archived IS FALSE
        ),
        intersections AS (
            SELECT
                f.id AS feature_id,
                f.layer_id,
                f.source_feature_id,
                f.geometry_hash AS feature_geometry_hash,
                f.properties,
                ss.site_area_sqm,
                ST_Intersection(
                    ss.geometry,
                    f.geometry
                ) AS intersection_geom
            FROM site_scope AS ss
            JOIN gis_features AS f
              ON f.project_id = ss.project_id
             AND f.layer_id = ANY(
                 CAST(:layer_ids AS uuid[])
             )
             AND f.is_archived IS FALSE
             AND ST_Intersects(
                 ss.geometry,
                 f.geometry
             )
        )
        SELECT
            feature_id,
            layer_id,
            source_feature_id,
            feature_geometry_hash,
            properties,
            site_area_sqm,
            CASE
              WHEN ST_Dimension(intersection_geom) = 2
              THEN ST_Area(
                  geography(intersection_geom)
              )
              ELSE 0.0
            END AS intersection_area_sqm
        FROM intersections
        """
    )

    rows = list(
        session.execute(
            sql,
            {
                "site_id": str(site_id),
                "project_id": str(project_id),
                "layer_ids": layer_ids,
                "require_active": site_state is SiteState.ACTIVE,
            },
        ).mappings()
    )

    matches: list[SiteApplicabilityMatch] = []

    for row in rows:
        site_area = float(
            row["site_area_sqm"]
        )
        intersection_area = float(
            row["intersection_area_sqm"]
        )

        # Boundary touching without polygon area is not treated as
        # an applicable planning polygon.
        if (
            site_area <= 0
            or intersection_area <= 0
        ):
            continue

        layer_id = uuid.UUID(
            str(row["layer_id"])
        )
        layer = layer_by_id.get(layer_id)

        if layer is None:
            continue

        role = _layer_role(layer)
        if role is None:
            continue

        site_overlap_percent = min(
            100.0,
            max(
                0.0,
                intersection_area
                / site_area
                * 100.0,
            ),
        )

        matches.append(
            SiteApplicabilityMatch(
                project_id=project_id,
                site_id=site_id,
                site_geometry_hash=(
                    scope.site.geometry_hash
                ),
                site_geometry_revision=(
                    scope.site.geometry_revision
                ),
                layer_id=layer.id,
                layer_name=layer.name,
                applicability_role=role,
                layer_provenance=(
                    layer.provenance or {}
                ),
                feature_id=uuid.UUID(
                    str(row["feature_id"])
                ),
                source_feature_id=(
                    row["source_feature_id"]
                ),
                feature_geometry_hash=str(
                    row[
                        "feature_geometry_hash"
                    ]
                ),
                properties=(
                    row["properties"] or {}
                ),
                intersection_area_sqm=(
                    intersection_area
                ),
                site_area_sqm=site_area,
                site_overlap_percent=(
                    site_overlap_percent
                ),
            )
        )

    matches.sort(
        key=lambda item: (
            item.applicability_role,
            -item.site_overlap_percent,
            item.layer_name.casefold(),
            str(item.feature_id),
        )
    )

    limitations: list[str] = []

    if not matches:
        limitations.append(
            (
                "Applicable GIS layers exist, but no "
                "positive-area polygon overlap was "
                "found with the active Site."
            )
        )

    return matches, limitations

