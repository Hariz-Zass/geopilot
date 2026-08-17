from __future__ import annotations

import io
import re
import uuid
from typing import Any

from fastapi import UploadFile
from pydantic import BaseModel, Field, field_validator
from shapely.geometry import shape
from shapely.prepared import prep
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.gis_feature import GISFeatureInput
from app.schemas.gis_layer import GISLayerCreateRequest
from app.schemas.site import SiteCreateRequest
from app.services.site_applicability import APPLICABILITY_ROLES
from app.services.track_b import TrackBError
from app.services.track_b_smart_import import prepare_import_plan
from app.services.track_b_smart_transactional_gis import (
    create_gis_layer_uncommitted,
    ingest_features_uncommitted,
)
from app.services.track_b_smart_transactional_site import (
    create_competition_site_uncommitted,
)

# SMART_ORGANIZER_PHASE2C3B_PERSISTENT_IMPORT_ALL

_ROLE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_BATCH_SIZE = 1000


class ImportAllRequest(BaseModel):
    site_name: str = Field(min_length=1, max_length=160)
    site_geometry: dict[str, Any]
    site_source_ref: str | None = Field(default=None, max_length=512)
    user_confirmed: bool = False
    role_assignments: dict[str, str] = Field(default_factory=dict)
    allow_invalid_geometry_skip: bool = False
    execute_persistent: bool = False

    @field_validator("role_assignments")
    @classmethod
    def validate_roles(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for key, role in value.items():
            logical_name = " ".join(str(key).split())
            normalized = str(role).strip().casefold()
            if not logical_name:
                raise ValueError("role assignment dataset name must not be blank")
            if not _ROLE.fullmatch(normalized):
                raise ValueError(
                    f"invalid role {role!r}; use a controlled lowercase slug such as land_use or transport_network"
                )
            cleaned[logical_name] = normalized
        return cleaned


def _valid_site_geometry(payload: dict[str, Any]):
    try:
        geom = shape(payload)
    except Exception as exc:
        raise TrackBError(f"Competition Site geometry is invalid: {exc}") from exc
    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise TrackBError("Competition Site geometry must be Polygon or MultiPolygon.")
    if geom.is_empty or not geom.is_valid:
        raise TrackBError("Competition Site geometry must be valid and non-empty.")
    minx, miny, maxx, maxy = geom.bounds
    if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
        raise TrackBError("Competition Site geometry must be EPSG:4326 longitude/latitude.")
    return geom


def _feature_geometry(feature: dict[str, Any]):
    geometry = feature.get("geometry") if isinstance(feature, dict) else None
    if not isinstance(geometry, dict):
        return None
    try:
        geom = shape(geometry)
    except Exception:
        return None
    if geom.is_empty or not geom.is_valid:
        return None
    return geom


def _layer_geometry_type(types: set[str]) -> str:
    if not types:
        return "Unknown"
    if len(types) == 1:
        return next(iter(types))
    return "Mixed"


def _safe_name(value: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    return cleaned[:limit] or "Organizer GIS"


async def execute_persistent_import_all(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    files: list[UploadFile],
    request: ImportAllRequest,
) -> dict[str, Any]:
    """
    Smart Organizer persistent GIS import orchestrator.

    One caller-owned transaction covers:
      Competition Site create/reuse -> GISLayer create/reuse -> GISFeature ingest.

    Persistent execution requires:
      - explicit user Site confirmation;
      - at least one spatially intersecting dataset;
      - explicit role assignment for every import candidate;
      - no invalid geometry in a candidate dataset unless explicitly allowed.
    """
    if not request.user_confirmed:
        raise TrackBError("Explicit user confirmation is required before Import All.")
    if not files:
        raise TrackBError("Import All requires at least one organizer file.")

    site_geom = _valid_site_geometry(request.site_geometry)
    prepared_site = prep(site_geom)

    cloned: list[UploadFile] = []
    raw_limit = 0
    for upload in files:
        data = await upload.read()
        raw_limit += len(data)
        cloned.append(UploadFile(filename=upload.filename, file=io.BytesIO(data)))

    phase2a = await prepare_import_plan(cloned)

    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []

    for dataset in phase2a.get("normalized_datasets", []):
        normalized = dataset.get("normalized") or {}
        features = (normalized.get("geojson") or {}).get("features") or []
        valid_intersections: list[dict[str, Any]] = []
        invalid_count = 0
        geometry_types: set[str] = set()

        for feature in features:
            geom = _feature_geometry(feature)
            if geom is None:
                invalid_count += 1
                continue
            if prepared_site.intersects(geom):
                valid_intersections.append(feature)
                geometry_types.add(geom.geom_type)

        logical_name = str(dataset.get("logical_name") or "").strip()

        if not features:
            skipped.append({
                "logical_name": logical_name,
                "decision": "SKIP_EMPTY",
                "source_feature_count": 0,
            })
            continue

        if not valid_intersections:
            if invalid_count == len(features):
                reviews.append({
                    "logical_name": logical_name,
                    "decision": "REVIEW_INVALID_GEOMETRY",
                    "source_feature_count": len(features),
                    "invalid_geometry_count": invalid_count,
                })
            else:
                skipped.append({
                    "logical_name": logical_name,
                    "decision": "SKIP_NO_OVERLAP",
                    "source_feature_count": len(features),
                    "invalid_geometry_count": invalid_count,
                })
            continue

        role = request.role_assignments.get(logical_name)
        if role is None:
            raise TrackBError(
                f"Import candidate {logical_name!r} requires an explicit confirmed data/applicability role."
            )

        if invalid_count and not request.allow_invalid_geometry_skip:
            raise TrackBError(
                f"Import candidate {logical_name!r} contains {invalid_count} invalid/unreadable geometries. "
                "Resolve the source or explicitly allow invalid geometry skip before persistent import."
            )

        candidates.append({
            "dataset": dataset,
            "logical_name": logical_name,
            "role": role,
            "features": valid_intersections,
            "invalid_geometry_count": invalid_count,
            "geometry_types": geometry_types,
        })

    if reviews:
        names = ", ".join(item["logical_name"] for item in reviews)
        raise TrackBError(
            f"Import All is blocked because dataset(s) require geometry review: {names}"
        )

    if not candidates:
        return {
            "phase": "phase2c3b_persistent_import_all",
            "status": "blocked_no_import_candidates",
            "database_writes": False,
            "committed": False,
            "site_created": False,
            "layers_created": 0,
            "features_created": 0,
            "skipped": skipped,
            "reviews": reviews,
            "message": "No organizer GIS dataset spatially intersects the confirmed competition Site.",
        }

    plan_summary = [{
        "logical_name": item["logical_name"],
        "role": item["role"],
        "intersecting_feature_count": len(item["features"]),
        "invalid_geometry_count": item["invalid_geometry_count"],
        "geometry_type": _layer_geometry_type(item["geometry_types"]),
        "source_checksum_sha256": item["dataset"].get("source_checksum_sha256"),
    } for item in candidates]

    if not request.execute_persistent:
        return {
            "phase": "phase2c3b_persistent_import_all",
            "status": "ready_for_commit",
            "database_writes": False,
            "committed": False,
            "site_created": False,
            "layers_created": 0,
            "features_created": 0,
            "import_plan": plan_summary,
            "skipped": skipped,
            "reviews": reviews,
            "message": "Persistent execution is disabled. Set execute_persistent=true after reviewing the plan.",
        }

    created_layers = 0
    reused_layers = 0
    created_features = 0
    duplicate_features = 0
    imported_layers: list[dict[str, Any]] = []

    try:
        site_result = create_competition_site_uncommitted(
            session,
            owner=owner,
            project_id=project_id,
            request=SiteCreateRequest(
                name=request.site_name,
                geometry=request.site_geometry,
                is_active=True,
            ),
        )
        site = site_result.site

        for item in candidates:
            dataset = item["dataset"]
            normalized = dataset.get("normalized") or {}
            role = item["role"]
            logical_name = item["logical_name"]
            source_members = dataset.get("source_members") or []

            provenance: dict[str, Any] = {
                "evidence_scope": "organizer_supplied_only",
                "competition_track": "B",
                "data_role": role,
                "ingestion_method": "smart_organizer_phase2c3b_import_all",
                "spatial_filter": "intersects_confirmed_site_preserve_source_geometry",
                "confirmed_site_id": str(site.id),
                "confirmed_site_geometry_hash": site.geometry_hash,
                "site_source_ref": request.site_source_ref,
                "source_members": source_members,
                "invalid_geometry_skipped_count": item["invalid_geometry_count"],
            }
            if role in APPLICABILITY_ROLES:
                provenance["applicability_role"] = role

            layer_request = GISLayerCreateRequest(
                name=_safe_name(logical_name, 160),
                description="Smart Organizer controlled Site-scoped GIS import",
                source_kind="upload",
                source_name=_safe_name(
                    str(source_members[0] if source_members else logical_name),
                    255,
                ),
                source_checksum_sha256=dataset.get("source_checksum_sha256"),
                source_crs=str(normalized.get("normalized_crs") or "EPSG:4326"),
                geometry_type=_layer_geometry_type(item["geometry_types"]),
                provenance=provenance,
                is_active=True,
            )

            layer_result = create_gis_layer_uncommitted(
                session,
                owner=owner,
                project_id=project_id,
                request=layer_request,
            )
            if layer_result.created:
                created_layers += 1
            else:
                reused_layers += 1

            feature_inputs: list[GISFeatureInput] = []
            for feature in item["features"]:
                feature_inputs.append(
                    GISFeatureInput(
                        type="Feature",
                        id=feature.get("id"),
                        geometry=feature["geometry"],
                        properties=feature.get("properties") or {},
                    )
                )

            layer_created_features = 0
            layer_duplicate_features = 0
            for start in range(0, len(feature_inputs), _BATCH_SIZE):
                batch = ingest_features_uncommitted(
                    session,
                    layer=layer_result.layer,
                    features=feature_inputs[start:start + _BATCH_SIZE],
                )
                created_features += batch.created_count
                duplicate_features += batch.duplicate_count
                layer_created_features += batch.created_count
                layer_duplicate_features += batch.duplicate_count

            imported_layers.append({
                "logical_name": logical_name,
                "layer_id": str(layer_result.layer.id),
                "role": role,
                "layer_created": layer_result.created,
                "feature_created_count": layer_created_features,
                "feature_duplicate_count": layer_duplicate_features,
            })

        session.commit()

        return {
            "phase": "phase2c3b_persistent_import_all",
            "status": "committed",
            "database_writes": True,
            "committed": True,
            "site_id": str(site.id),
            "site_created": site_result.created,
            "site_duplicate_reused": site_result.duplicate,
            "layers_created": created_layers,
            "layers_reused": reused_layers,
            "features_created": created_features,
            "features_duplicates_skipped": duplicate_features,
            "imported_layers": imported_layers,
            "skipped": skipped,
            "reviews": reviews,
        }
    except Exception:
        session.rollback()
        raise
