from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.models.gis_layer import GISLayer
from app.models.user import User
from app.schemas.gis_feature import GISFeatureCollectionRequest
from app.schemas.gis_layer import GISLayerCreateRequest
from app.services.gis_features import ingest_feature_collection
from app.services.gis_layers import create_gis_layer

PlanningApplicabilityRole = Literal[
    "zoning",
    "land_use",
    "planning_block",
    "planning_subzone",
]

_ALLOWED_ROLES = {
    "zoning",
    "land_use",
    "planning_block",
    "planning_subzone",
}


class PlanningSpatialEvidenceError(Exception):
    pass


class PlanningSpatialEvidenceImportRequest(BaseModel):
    layer_name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    applicability_role: PlanningApplicabilityRole
    authority: str = Field(min_length=2, max_length=255)
    jurisdiction: str = Field(min_length=2, max_length=255)
    source_title: str = Field(min_length=2, max_length=500)
    source_kind: Literal["upload", "acquired", "external_reference"] = "upload"
    source_name: str | None = Field(default=None, max_length=255)
    source_uri: str | None = Field(default=None, max_length=4096)
    source_crs: str = "EPSG:4326"
    provenance_extra: dict[str, Any] = Field(default_factory=dict)
    geojson: dict[str, Any]

    @field_validator(
        "layer_name",
        "authority",
        "jurisdiction",
        "source_title",
        mode="before",
    )
    @classmethod
    def _clean_required_text(cls, value):
        if isinstance(value, str):
            value = " ".join(value.split())
        return value

    @field_validator("source_name", "source_uri", mode="before")
    @classmethod
    def _clean_optional_text(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def _controlled_source_contract(self):
        if self.source_crs.strip().upper() != "EPSG:4326":
            raise ValueError(
                "Planning Spatial Evidence V1 accepts only EPSG:4326 GeoJSON."
            )

        if self.source_kind == "upload" and not self.source_name:
            raise ValueError("upload planning layers require source_name")

        if self.source_kind in {"acquired", "external_reference"} and not self.source_uri:
            raise ValueError(
                f"{self.source_kind} planning layers require source_uri"
            )

        role = self.applicability_role.strip().casefold()
        if role not in _ALLOWED_ROLES:
            raise ValueError("unsupported planning applicability_role")

        return self


@dataclass(frozen=True, slots=True)
class PlanningSpatialEvidenceImportResult:
    layer: GISLayer
    feature_count: int
    applicability_role: str
    checksum_sha256: str


def _canonical_geojson_bytes(payload: dict[str, Any]) -> bytes:
    try:
        rendered = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PlanningSpatialEvidenceError(
            "Planning spatial GeoJSON must be finite JSON."
        ) from exc
    return rendered.encode("utf-8")


def _validated_collection(payload: dict[str, Any]) -> GISFeatureCollectionRequest:
    if not isinstance(payload, dict):
        raise PlanningSpatialEvidenceError(
            "Planning spatial evidence must be a GeoJSON object."
        )

    if payload.get("type") != "FeatureCollection":
        raise PlanningSpatialEvidenceError(
            "Planning spatial evidence must be a GeoJSON FeatureCollection."
        )

    try:
        request = GISFeatureCollectionRequest.model_validate(payload)
    except Exception as exc:
        raise PlanningSpatialEvidenceError(
            f"Planning spatial GeoJSON validation failed: {exc}"
        ) from exc

    for item in request.features:
        if item.geometry.type not in {"Polygon", "MultiPolygon"}:
            raise PlanningSpatialEvidenceError(
                "Planning applicability evidence must contain only Polygon "
                "or MultiPolygon features."
            )

    return request


def import_planning_spatial_evidence(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    request: PlanningSpatialEvidenceImportRequest,
) -> PlanningSpatialEvidenceImportResult:
    """
    Controlled planning-polygon ingestion foundation.

    This function deliberately reuses GeoPilot's existing GISLayer/GISFeature
    services. It does not infer zoning from names, bypass project ownership,
    or write raw SQL.
    """
    collection = _validated_collection(request.geojson)
    checksum = hashlib.sha256(
        _canonical_geojson_bytes(request.geojson)
    ).hexdigest()

    provenance = dict(request.provenance_extra or {})
    provenance.update(
        {
            "applicability_role": request.applicability_role,
            "evidence_domain": "planning",
            "authority": request.authority,
            "jurisdiction": request.jurisdiction,
            "source_title": request.source_title,
            "source_status": "controlled_import",
            "import_method": "planning_spatial_evidence_foundation_v1",
            "source_crs": "EPSG:4326",
            "source_checksum_sha256": checksum,
        }
    )

    layer_request = GISLayerCreateRequest(
        name=request.layer_name,
        description=request.description,
        source_kind=request.source_kind,
        source_name=request.source_name,
        source_uri=request.source_uri,
        source_checksum_sha256=checksum,
        source_crs="EPSG:4326",
        geometry_type=None,
        provenance=provenance,
        is_active=True,
    )

    layer = create_gis_layer(
        session,
        owner=owner,
        project_id=project_id,
        request=layer_request,
    )

    try:
        features = ingest_feature_collection(
            session,
            owner=owner,
            project_id=project_id,
            layer_id=layer.id,
            request=collection,
        )
    except Exception:
        # Avoid leaving an empty planning layer behind when feature ingestion
        # fails. The existing service transaction protects feature writes.
        session.delete(layer)
        session.commit()
        raise

    return PlanningSpatialEvidenceImportResult(
        layer=layer,
        feature_count=len(features),
        applicability_role=request.applicability_role,
        checksum_sha256=checksum,
    )
