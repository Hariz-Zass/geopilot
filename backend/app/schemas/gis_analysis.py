from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


GIS_ANALYSIS_METHOD_VERSION = "postgis-geography-v1"


class DeterministicAnalysisBase(BaseModel):
    deterministic: Literal[True] = True
    method_version: Literal["postgis-geography-v1"] = GIS_ANALYSIS_METHOD_VERSION
    project_id: uuid.UUID
    site_id: uuid.UUID
    site_geometry_hash: str
    site_geometry_revision: int


class SiteAreaResult(DeterministicAnalysisBase):
    analysis_type: Literal["site_area"] = "site_area"
    area_sqm: float = Field(ge=0)
    area_hectares: float = Field(ge=0)


class FeatureDistanceResult(DeterministicAnalysisBase):
    analysis_type: Literal["feature_distance"] = "feature_distance"
    layer_id: uuid.UUID
    feature_id: uuid.UUID
    feature_geometry_hash: str
    distance_m: float = Field(ge=0)


class NearestFeatureItem(BaseModel):
    feature_id: uuid.UUID
    source_feature_id: str | None = None
    geometry_type: str
    geometry_hash: str
    properties: dict[str, Any]
    distance_m: float = Field(ge=0)


class NearestFeaturesResult(DeterministicAnalysisBase):
    analysis_type: Literal["nearest_features"] = "nearest_features"
    layer_id: uuid.UUID
    max_distance_m: float | None = Field(default=None, gt=0)
    items: list[NearestFeatureItem]


class FeatureOverlapResult(DeterministicAnalysisBase):
    analysis_type: Literal["feature_overlap"] = "feature_overlap"
    layer_id: uuid.UUID
    feature_id: uuid.UUID
    feature_geometry_hash: str
    intersects: bool
    intersection_area_sqm: float = Field(ge=0)
    site_area_sqm: float = Field(ge=0)
    site_overlap_percent: float = Field(ge=0, le=100)
    feature_area_sqm: float | None = Field(default=None, ge=0)
    feature_overlap_percent: float | None = Field(default=None, ge=0, le=100)


class SiteBufferRequest(BaseModel):
    distance_m: float = Field(gt=0, le=100_000)


class SiteBufferResult(DeterministicAnalysisBase):
    analysis_type: Literal["site_buffer"] = "site_buffer"
    distance_m: float = Field(gt=0)
    buffer_area_sqm: float = Field(ge=0)
    geometry: dict[str, Any]
    geometry_role: Literal["ephemeral_server_derived"] = "ephemeral_server_derived"

    @model_validator(mode="after")
    def validate_geometry(self) -> "SiteBufferResult":
        if self.geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError("buffer geometry must be Polygon or MultiPolygon")
        return self
