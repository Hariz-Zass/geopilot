from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.planning_run import PlanningRun
from app.services.isolation import SiteState
from app.schemas.tool_evidence import (
    EvidenceSourceRef,
    ToolEvidence,
)
from app.services.gis_analysis import calculate_site_area
from app.services.terrain_analysis import calculate_site_terrain_summary
from sqlalchemy import text

from app.services.site_context_acquisition import (
    OpenStreetMapOverpassProvider,
    SiteContextAcquisitionError,
)
from app.services.site_context_evidence import (
    select_site_context_evidence,
)

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
    "context.site_surroundings": ToolSpec(
        "context.site_surroundings",
        "context",
        False,
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


def execute_latest_temporal_ndvi(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    exclude_run_id: uuid.UUID | None = None,
    preferred_analysis_id: uuid.UUID | None = None,
) -> ToolEvidence | None:
    """
    Recall the newest persisted, validated satellite.temporal_ndvi evidence
    already produced inside the same authorized project/site scope.

    This does not recalculate imagery and does not infer change from a basemap.
    """
    stmt = (
        select(PlanningRun)
        .where(
            PlanningRun.project_id == project_id,
            PlanningRun.site_id == site_id,
            PlanningRun.created_by_user_id == owner.id,
        )
        .order_by(PlanningRun.created_at.desc())
    )

    runs = list(session.scalars(stmt))

    for run in runs:
        if exclude_run_id is not None and run.id == exclude_run_id:
            continue

        raw_evidence = run.evidence or []

        for raw in reversed(raw_evidence):
            if not isinstance(raw, dict):
                continue

            if raw.get("tool_name") != "satellite.temporal_ndvi":
                continue

            if raw.get("status") != "measured":
                continue

            if str(raw.get("project_id")) != str(project_id):
                continue

            if str(raw.get("site_id")) != str(site_id):
                continue

            try:
                evidence = ToolEvidence.model_validate(raw)
            except Exception:
                continue

            return evidence

    # TRACK_B_TEMPORAL_MANIFEST_RECALL_BRIDGE_V1
    #
    # Track B persists validated temporal analyses independently from
    # PlanningRun evidence:
    #
    #   <raster_storage_root>/analysis/<project_id>/<analysis_id>/analysis.json
    #
    # PlanningRun remains the first recall source. The manifest bridge is a
    # read-only fallback and never recalculates imagery or invents evidence.
    from app.core.config import get_settings

    root = Path(
        get_settings().raster_storage_root
    ).expanduser().resolve()

    project_analysis_root = (
        root / "analysis" / str(project_id)
    ).resolve()

    if (
        root != project_analysis_root
        and root not in project_analysis_root.parents
    ):
        return None

    if not project_analysis_root.is_dir():
        return None

    candidates: list[
        tuple[bool, float, Path, dict]
    ] = []

    for manifest_path in project_analysis_root.glob(
        "*/analysis.json"
    ):
        try:
            resolved = manifest_path.resolve()

            if (
                project_analysis_root != resolved
                and project_analysis_root not in resolved.parents
            ):
                continue

            raw_manifest = json.loads(
                resolved.read_text(encoding="utf-8")
            )

            if not isinstance(raw_manifest, dict):
                continue

            manifest_project_id = raw_manifest.get(
                "project_id"
            )

            if (
                manifest_project_id is not None
                and str(manifest_project_id) != str(project_id)
            ):
                continue

            manifest_site_id = raw_manifest.get("site_id")

            if (
                manifest_site_id is None
                or str(manifest_site_id) != str(site_id)
            ):
                continue

            mode = str(
                raw_manifest.get("mode") or ""
            ).casefold()

            if mode != "ndvi":
                continue

            changed_percentage = raw_manifest.get(
                "changed_percentage"
            )
            changed_pixel_count = raw_manifest.get(
                "changed_pixel_count"
            )
            usable_coverage_percent = raw_manifest.get(
                "usable_coverage_percent"
            )

            if (
                changed_percentage is None
                or changed_pixel_count is None
                or usable_coverage_percent is None
            ):
                continue

            evidence_items = raw_manifest.get(
                "evidence"
            )

            if (
                not isinstance(evidence_items, list)
                or len(evidence_items) < 2
            ):
                continue

            raster_sources = [
                item
                for item in evidence_items
                if isinstance(item, dict)
                and item.get("kind") == "raster_dataset"
                and item.get("id")
                and item.get("checksum_sha256")
            ]

            if len(raster_sources) < 2:
                continue

            analysis_id = raw_manifest.get(
                "analysis_id"
            ) or resolved.parent.name

            try:
                uuid.UUID(str(analysis_id))
            except (ValueError, TypeError, AttributeError):
                continue

            is_preferred = (
                preferred_analysis_id is not None
                and str(analysis_id) == str(preferred_analysis_id)
            )

            candidates.append(
                (
                    is_preferred,
                    resolved.stat().st_mtime,
                    resolved,
                    raw_manifest,
                )
            )

        except (
            OSError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ):
            continue

    if not candidates:
        return None

    if preferred_analysis_id is not None:
        preferred_candidates = [
            item
            for item in candidates
            if item[0]
        ]

        # Explicit active-analysis context is authoritative.
        # Never silently substitute another analysis.
        if not preferred_candidates:
            return None

        _, _, manifest_path, manifest = max(
            preferred_candidates,
            key=lambda item: item[1],
        )
    else:
        _, _, manifest_path, manifest = max(
            candidates,
            key=lambda item: item[1],
        )

    source_refs: list[EvidenceSourceRef] = []

    allowed_source_kinds = {
        "document_chunk",
        "policy_reference",
        "compliance_fact",
        "compliance_finding",
        "suitability_result",
        "gis_feature",
        "raster_dataset",
        "temporal_measurement",
        "user_input",
        "external_provider",
    }

    for item in manifest.get("evidence", []):
        if not isinstance(item, dict):
            continue

        source_id = item.get("id")
        source_kind = str(item.get("kind") or "")

        if not source_id:
            continue

        # Track B manifests can contain provenance records such as
        # site_geometry. ToolEvidence source refs intentionally accept only
        # the canonical evidence kinds defined by the planning contract.
        if source_kind not in allowed_source_kinds:
            continue

        source_refs.append(
            EvidenceSourceRef(
                kind=source_kind,
                id=source_id,
                hash=(
                    item.get("checksum_sha256")
                    or item.get("geometry_hash")
                ),
            )
        )

    payload = dict(manifest)

    payload["analysis_id"] = str(
        manifest.get("analysis_id")
        or manifest_path.parent.name
    )

    payload["persistence_source"] = (
        "track_b_analysis_manifest"
    )

    payload["manifest_path"] = str(
        manifest_path.relative_to(root)
    )

    return ToolEvidence(
        project_id=project_id,
        site_id=site_id,
        tool_name="satellite.temporal_ndvi",
        deterministic=True,
        status="measured",
        payload=payload,
        sources=source_refs,
        limitations=[
            (
                "Recalled read-only from a persisted validated "
                "Track B temporal analysis manifest."
            ),
            (
                "Spectral or NDVI change does not by itself prove "
                "development, land-use conversion, causation, "
                "illegality, or statutory non-compliance."
            ),
        ],
    )

def execute_site_context(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> tuple[list[ToolEvidence], list[str]]:
    """
    Acquire live project/site-scoped OpenStreetMap context,
    rank planning-relevant features, and expose only selected
    evidence through the Planning Officer evidence contract.

    No acquired OSM feature is persisted by this function.
    """

    # Reuse the existing authorization/isolation path before
    # any external acquisition occurs.
    calculate_site_area(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )

    geometry_json = session.scalar(
        text(
            """
            SELECT ST_AsGeoJSON(geometry)
            FROM sites
            WHERE id = :site_id
              AND project_id = :project_id
            """
        ),
        {
            "site_id": site_id,
            "project_id": project_id,
        },
    )

    if not geometry_json:
        return [], [
            (
                "Site context acquisition could not resolve "
                "the active Site geometry."
            )
        ]

    import json

    try:
        site_geometry = json.loads(geometry_json)
    except (TypeError, ValueError):
        return [], [
            "Active Site geometry could not be decoded as GeoJSON."
        ]

    provider = OpenStreetMapOverpassProvider()

    try:
        acquired = provider.acquire(
            site_geometry=site_geometry,
            buffer_meters=1000.0,
            max_features=500,
        )
    except SiteContextAcquisitionError as exc:
        return [], [
            f"Site context provider unavailable: {exc}"
        ]

    selection = select_site_context_evidence(
        site_geometry=site_geometry,
        features=acquired.features,
        max_per_category=5,
        max_total=40,
    )

    evidence: list[ToolEvidence] = []

    for item in selection.selected:
        evidence.append(
            ToolEvidence(
                project_id=project_id,
                site_id=site_id,
                tool_name="context.site_surroundings",
                deterministic=False,
                status="retrieved",
                payload={
                    "provider": item.provider,
                    "source_feature_id": item.source_feature_id,
                    "name": item.name,
                    "planning_category": item.planning_category,
                    "subtype": item.subtype,
                    "geometry_type": item.geometry_type,
                    "distance_meters": item.distance_meters,
                    "spatial_relation": item.spatial_relation,
                    "ranking_score": item.score,
                    "properties": item.properties,
                    "query_bbox": list(acquired.query_bbox),
                    "buffer_meters": acquired.buffer_meters,
                    "source_feature_count": (
                        selection.source_feature_count
                    ),
                    "eligible_feature_count": (
                        selection.eligible_feature_count
                    ),
                    "selected_feature_count": (
                        selection.selected_feature_count
                    ),
                    "category_counts": selection.category_counts,
                    "provider_truncated": acquired.truncated,
                },
                sources=[
                    EvidenceSourceRef(
                        kind="external_provider",
                        id=(
                            f"openstreetmap:"
                            f"{item.source_feature_id}"
                        ),
                    )
                ],
                limitations=[
                    (
                        "OpenStreetMap site-context evidence is "
                        "provider-sourced contextual evidence and "
                        "must not be treated as statutory zoning, "
                        "legal parcel, approval, or authoritative "
                        "planning-policy evidence."
                    )
                ],
            )
        )

    if not evidence:
        return [], [
            (
                "OpenStreetMap acquisition completed but no "
                "planning-relevant site-context evidence was selected."
            )
        ]

    limitations: list[str] = []

    if acquired.truncated:
        limitations.append(
            (
                "OpenStreetMap provider results reached the configured "
                "feature limit; site-context evidence may be incomplete."
            )
        )

    return evidence, limitations
