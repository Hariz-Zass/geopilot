from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field
from shapely.geometry import shape, mapping
from shapely.validation import explain_validity

from app.services.track_b import TrackBError

# SMART_ORGANIZER_PHASE2B3_SITE_RESOLUTION

ResolutionMode = Literal[
    "organizer_candidate",
    "uploaded_boundary",
    "manual_draw",
]


class SiteResolutionRequest(BaseModel):
    site_name: str = Field(min_length=1, max_length=160)
    mode: ResolutionMode
    geometry: dict[str, Any]
    source_ref: str | None = Field(default=None, max_length=512)
    user_confirmed: bool = False


def validate_site_resolution(request: SiteResolutionRequest) -> dict[str, Any]:
    if not request.user_confirmed:
        return {
            "phase": "phase2b3_site_resolution",
            "status": "confirmation_required",
            "database_writes": False,
            "migration_required": False,
            "site_name": request.site_name,
            "mode": request.mode,
            "source_ref": request.source_ref,
            "geometry_valid": False,
            "ready_for_site_creation": False,
            "limitations": [
                "Explicit user confirmation is required before a competition Site can be created."
            ],
        }

    try:
        geom = shape(request.geometry)
    except Exception as exc:
        raise TrackBError(f"Site boundary is not valid GeoJSON geometry: {exc}") from exc

    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise TrackBError(
            "Competition Site boundary must be Polygon or MultiPolygon."
        )
    if geom.is_empty:
        raise TrackBError("Competition Site boundary must not be empty.")
    if not geom.is_valid:
        raise TrackBError(
            f"Competition Site boundary is invalid: {explain_validity(geom)}"
        )

    minx, miny, maxx, maxy = geom.bounds
    if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
        raise TrackBError(
            "Competition Site boundary must be normalized to EPSG:4326 longitude/latitude."
        )

    return {
        "phase": "phase2b3_site_resolution",
        "status": "validated",
        "database_writes": False,
        "migration_required": False,
        "site_name": request.site_name.strip(),
        "mode": request.mode,
        "source_ref": request.source_ref,
        "geometry_valid": True,
        "geometry_type": geom.geom_type,
        "bounds": [minx, miny, maxx, maxy],
        "geometry": mapping(geom),
        "ready_for_site_creation": True,
        "site_create_payload_preview": {
            "name": request.site_name.strip(),
            "geometry": mapping(geom),
            "is_active": True,
        },
        "provenance_preview": {
            "source": "track_b_organizer_site_resolution",
            "resolution_mode": request.mode,
            "source_ref": request.source_ref,
            "user_confirmed": True,
            "crs": "EPSG:4326",
        },
        "limitations": [
            "This gate validates a user-confirmed competition Site boundary but does not create or modify database records.",
            "Boundary authority and organizer intent remain the responsibility of the participant to confirm from organizer-provided materials.",
        ],
        "next_action": "Create the confirmed Competition Site, then spatially scope organizer datasets before persistent Import All.",
    }


def parse_uploaded_boundary_geojson(
    *,
    site_name: str,
    payload: bytes,
    source_ref: str,
    user_confirmed: bool,
) -> dict[str, Any]:
    try:
        obj = json.loads(payload.decode("utf-8-sig"))
    except Exception as exc:
        raise TrackBError("Uploaded boundary is not valid UTF-8 GeoJSON/JSON.") from exc

    geometry: dict[str, Any] | None = None
    if isinstance(obj, dict) and obj.get("type") in {"Polygon", "MultiPolygon"}:
        geometry = obj
    elif isinstance(obj, dict) and obj.get("type") == "Feature":
        geometry = obj.get("geometry")
    elif isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
        features = obj.get("features") or []
        usable = [
            feature.get("geometry")
            for feature in features
            if isinstance(feature, dict)
            and isinstance(feature.get("geometry"), dict)
            and feature["geometry"].get("type") in {"Polygon", "MultiPolygon"}
        ]
        if len(usable) == 1:
            geometry = usable[0]
        elif len(usable) > 1:
            raise TrackBError(
                "Uploaded boundary contains multiple polygon features. Select/dissolve the intended competition Site explicitly before confirmation."
            )

    if geometry is None:
        raise TrackBError(
            "Uploaded boundary must contain exactly one Polygon/MultiPolygon competition Site geometry."
        )

    return validate_site_resolution(
        SiteResolutionRequest(
            site_name=site_name,
            mode="uploaded_boundary",
            geometry=geometry,
            source_ref=source_ref,
            user_confirmed=user_confirmed,
        )
    )
