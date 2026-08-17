from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.isolation import SiteState
from app.schemas.tool_evidence import (
    EvidenceSourceRef,
    ToolEvidence,
)
from app.services.gis_analysis import calculate_site_area
from app.services.terrain_analysis import calculate_site_terrain_summary
from app.services.site_applicability import (
    resolve_site_applicability,
)


class ToolRegistryError(Exception):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    domain: str
    deterministic: bool
    read_only: bool


APPROVED_TOOLS = {
    "gis.site_area": ToolSpec(
        "gis.site_area",
        "gis",
        True,
        True,
    ),
    "gis.site_applicability": ToolSpec(
        "gis.site_applicability",
        "gis",
        True,
        True,
    ),
    "documents.search": ToolSpec(
        "documents.search",
        "documents",
        False,
        True,
    ),
    "compliance.persisted_findings": ToolSpec(
        "compliance.persisted_findings",
        "compliance",
        True,
        True,
    ),
    "suitability.persisted_results": ToolSpec(
        "suitability.persisted_results",
        "suitability",
        True,
        True,
    ),
    "satellite.temporal_ndvi": ToolSpec(
        "satellite.temporal_ndvi",
        "satellite",
        True,
        True,
    ),
    "terrain.site_summary": ToolSpec(
        "terrain.site_summary",
        "terrain",
        True,
        True,
    ),
}


def get_tool(name: str) -> ToolSpec:
    if name not in APPROVED_TOOLS:
        raise ToolRegistryError(
            "Tool is not registered server-side."
        )

    return APPROVED_TOOLS[name]


def execute_site_area(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> ToolEvidence:
    result = calculate_site_area(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )

    return ToolEvidence(
        project_id=project_id,
        site_id=site_id,
        tool_name="gis.site_area",
        deterministic=True,
        status="measured",
        payload=result.model_dump(
            mode="json"
        ),
        sources=[
            EvidenceSourceRef(
                kind="user_input",
                id=f"site:{site_id}",
                hash=result.site_geometry_hash,
            )
        ],
        limitations=[
            (
                "Measured from the active "
                "server-owned Site geometry."
            )
        ],
    )


def execute_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> tuple[list[ToolEvidence], list[str]]:
    matches, limitations = (
        resolve_site_applicability(
            session,
            owner=owner,
            project_id=project_id,
            site_id=site_id,
            site_state=site_state,
        )
    )

    evidence: list[ToolEvidence] = []

    for match in matches:
        evidence.append(
            ToolEvidence(
                project_id=project_id,
                site_id=site_id,
                tool_name=(
                    "gis.site_applicability"
                ),
                deterministic=True,
                status="measured",
                payload={
                    "applicability_role": (
                        match.applicability_role
                    ),
                    "layer_id": str(
                        match.layer_id
                    ),
                    "layer_name": (
                        match.layer_name
                    ),
                    "layer_provenance": (
                        match.layer_provenance
                    ),
                    "feature_id": str(
                        match.feature_id
                    ),
                    "source_feature_id": (
                        match.source_feature_id
                    ),
                    "properties": (
                        match.properties
                    ),
                    "intersection_area_sqm": (
                        match.intersection_area_sqm
                    ),
                    "site_area_sqm": (
                        match.site_area_sqm
                    ),
                    "site_overlap_percent": (
                        match.site_overlap_percent
                    ),
                    "site_geometry_hash": (
                        match.site_geometry_hash
                    ),
                    "site_geometry_revision": (
                        match.site_geometry_revision
                    ),
                    "feature_geometry_hash": (
                        match.feature_geometry_hash
                    ),
                },
                sources=[
                    EvidenceSourceRef(
                        kind="gis_feature",
                        id=match.feature_id,
                        hash=(
                            match.feature_geometry_hash
                        ),
                    )
                ],
                limitations=[
                    (
                        "Spatial applicability is "
                        "measured only from the "
                        "server-owned Site geometry "
                        "and the intersecting "
                        "classified GIS feature."
                    )
                ],
                geometry_reference={
                    "site_geometry_hash": (
                        match.site_geometry_hash
                    ),
                    "site_geometry_revision": (
                        match.site_geometry_revision
                    ),
                    "feature_geometry_hash": (
                        match.feature_geometry_hash
                    ),
                },
            )
        )

    return evidence, limitations


def execute_site_terrain_summary(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> ToolEvidence:
    result = calculate_site_terrain_summary(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
    )
    return ToolEvidence(
        project_id=project_id,
        site_id=site_id,
        tool_name="terrain.site_summary",
        deterministic=True,
        status="measured",
        payload={
            "raster_id": str(result.raster_id),
            "crs": result.crs,
            "valid_pixel_count": result.valid_pixel_count,
            "elevation_min_m": result.elevation_min_m,
            "elevation_max_m": result.elevation_max_m,
            "elevation_mean_m": result.elevation_mean_m,
            "slope_min_degrees": result.slope_min_degrees,
            "slope_max_degrees": result.slope_max_degrees,
            "slope_mean_degrees": result.slope_mean_degrees,
            "max_slope_longitude": result.max_slope_longitude,
            "max_slope_latitude": result.max_slope_latitude,
        },
        sources=[
            EvidenceSourceRef(
                kind="raster_dataset",
                id=result.raster_id,
                hash=result.raster_checksum_sha256,
            )
        ],
        limitations=[
            "Terrain values are deterministically derived from the selected "
            "project/site-scoped DEM within the active Site geometry."
        ],
    )
