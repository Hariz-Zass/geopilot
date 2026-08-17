from __future__ import annotations

import io
from typing import Any

from fastapi import UploadFile
from shapely.geometry import shape
from shapely.prepared import prep

from app.core.config import get_settings
from app.services.track_b import TrackBError
from app.services.track_b_smart_import import prepare_import_plan

# SMART_ORGANIZER_PHASE2C2_SPATIAL_IMPORT_PLAN


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


async def build_spatial_import_plan(
    *,
    files: list[UploadFile],
    site_geometry: dict[str, Any],
    site_name: str,
    site_source_ref: str | None,
    user_confirmed: bool,
) -> dict[str, Any]:
    if not user_confirmed:
        raise TrackBError(
            "Spatial import planning requires an explicitly user-confirmed competition Site boundary."
        )

    try:
        site_geom = shape(site_geometry)
    except Exception as exc:
        raise TrackBError(f"Competition Site geometry is invalid: {exc}") from exc

    if site_geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise TrackBError("Competition Site geometry must be Polygon or MultiPolygon.")
    if site_geom.is_empty or not site_geom.is_valid:
        raise TrackBError("Competition Site geometry must be valid and non-empty.")

    minx, miny, maxx, maxy = site_geom.bounds
    if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
        raise TrackBError("Competition Site geometry must be EPSG:4326 longitude/latitude.")

    limit = max(
        int(get_settings().raster_upload_max_bytes),
        int(get_settings().document_upload_max_bytes),
    )
    cloned: list[UploadFile] = []
    for upload in files:
        data = await upload.read(limit + 1)
        if len(data) > limit:
            raise TrackBError(f"Organizer file exceeds configured limit: {upload.filename}")
        cloned.append(UploadFile(filename=upload.filename, file=io.BytesIO(data)))

    prepared_site = prep(site_geom)
    phase2a = await prepare_import_plan(cloned)

    datasets: list[dict[str, Any]] = []
    totals = {
        "source_features": 0,
        "valid_geometry_features": 0,
        "intersecting_features": 0,
        "import_candidate_datasets": 0,
        "skip_empty_datasets": 0,
        "skip_no_overlap_datasets": 0,
        "review_datasets": 0,
    }

    for dataset in phase2a.get("normalized_datasets", []):
        normalized = dataset.get("normalized") or {}
        features = (normalized.get("geojson") or {}).get("features") or []
        source_count = len(features)
        totals["source_features"] += source_count

        valid_count = 0
        intersecting_count = 0
        invalid_geometry_count = 0
        geometry_types: set[str] = set()
        intersecting_geometry_types: set[str] = set()

        for feature in features:
            geom = _feature_geometry(feature)
            if geom is None:
                invalid_geometry_count += 1
                continue

            valid_count += 1
            geometry_types.add(geom.geom_type)

            try:
                hit = prepared_site.intersects(geom)
            except Exception:
                hit = geom.intersects(site_geom)

            if hit:
                intersecting_count += 1
                intersecting_geometry_types.add(geom.geom_type)

        totals["valid_geometry_features"] += valid_count
        totals["intersecting_features"] += intersecting_count

        if source_count == 0:
            decision = "SKIP_EMPTY"
            reason = "Dataset contains no features."
            totals["skip_empty_datasets"] += 1
        elif valid_count == 0:
            decision = "REVIEW_INVALID_GEOMETRY"
            reason = "Dataset contains features but no valid usable geometry."
            totals["review_datasets"] += 1
        elif intersecting_count == 0:
            decision = "SKIP_NO_OVERLAP"
            reason = "No valid feature geometry intersects the confirmed competition Site."
            totals["skip_no_overlap_datasets"] += 1
        else:
            decision = "IMPORT_CANDIDATE"
            reason = "One or more valid features intersect the confirmed competition Site."
            totals["import_candidate_datasets"] += 1

        ratio = (
            round((intersecting_count / source_count) * 100.0, 8)
            if source_count > 0
            else 0.0
        )

        datasets.append({
            "logical_name": dataset.get("logical_name"),
            "format": dataset.get("format"),
            "source_members": dataset.get("source_members"),
            "source_checksum_sha256": dataset.get("source_checksum_sha256"),
            "normalized_crs": normalized.get("normalized_crs"),
            "source_feature_count": source_count,
            "valid_geometry_feature_count": valid_count,
            "invalid_geometry_feature_count": invalid_geometry_count,
            "intersecting_feature_count": intersecting_count,
            "intersection_ratio_percent": ratio,
            "geometry_types": sorted(geometry_types),
            "intersecting_geometry_types": sorted(intersecting_geometry_types),
            "decision": decision,
            "decision_reason": reason,
            "applicability_role": None,
            "role_confirmation_required": decision == "IMPORT_CANDIDATE",
            "persistent_write_authorized": False,
        })

    return {
        "phase": "phase2c2_spatial_import_planning",
        "database_writes": False,
        "migration_required": False,
        "site": {
            "name": site_name,
            "source_ref": site_source_ref,
            "user_confirmed": True,
            "geometry_type": site_geom.geom_type,
            "bounds": [minx, miny, maxx, maxy],
            "crs": "EPSG:4326",
        },
        "dataset_count": len(datasets),
        "datasets": datasets,
        "totals": totals,
        "blocking_conditions": [
            "Every IMPORT_CANDIDATE dataset still requires an explicit applicability/data role before persistent GIS import.",
            "This planning gate does not create a Site, GISLayer, GISFeature, raster record, or planning document record.",
        ],
        "ready_for_phase2c3": (
            totals["import_candidate_datasets"] > 0
            and totals["review_datasets"] == 0
        ),
        "next_action": (
            "Confirm roles for IMPORT_CANDIDATE datasets, then execute one caller-owned transaction for confirmed Site creation and spatially scoped Import All."
        ),
    }
