from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FactValueType = Literal["numeric", "text", "boolean", "set"]


class UserSuppliedComplianceFactCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_key: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9_.:-]*$")
    label: str = Field(min_length=1, max_length=255)
    value_type: FactValueType
    unit: str | None = Field(default=None, max_length=80)
    numeric_value: Decimal | None = None
    text_value: str | None = Field(default=None, min_length=1, max_length=6000)
    boolean_value: bool | None = None
    set_value: list[str] | None = Field(default=None, min_length=1, max_length=100)
    source_description: str = Field(min_length=1, max_length=6000)

    @model_validator(mode="after")
    def validate_value_shape(self):
        present = {
            "numeric": self.numeric_value is not None,
            "text": self.text_value is not None,
            "boolean": self.boolean_value is not None,
            "set": self.set_value is not None,
        }
        if not present[self.value_type] or sum(present.values()) != 1:
            raise ValueError("exactly one value payload matching value_type is required")
        if self.set_value is not None:
            values = [v.strip() for v in self.set_value if v.strip()]
            if not values or len(values) != len({v.casefold() for v in values}):
                raise ValueError("set_value entries must be non-empty and unique")
            self.set_value = values
        return self


class GISDerivedComplianceFactCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_type: Literal["site_area", "feature_distance"]
    metric_key: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9_.:-]*$")
    label: str = Field(min_length=1, max_length=255)
    output_field: Literal["area_sqm", "area_hectares", "distance_m"]
    layer_id: uuid.UUID | None = None
    feature_id: uuid.UUID | None = None
    source_description: str | None = Field(default=None, max_length=6000)

    @model_validator(mode="after")
    def validate_analysis_shape(self):
        if self.analysis_type == "site_area":
            if self.output_field not in {"area_sqm", "area_hectares"}:
                raise ValueError("site_area may only persist area_sqm or area_hectares")
            if self.layer_id is not None or self.feature_id is not None:
                raise ValueError("site_area does not accept layer_id/feature_id")
        else:
            if self.output_field != "distance_m":
                raise ValueError("feature_distance may only persist distance_m")
            if self.layer_id is None or self.feature_id is None:
                raise ValueError("feature_distance requires layer_id and feature_id")
        return self


class ComplianceFactUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_archived: bool


class ComplianceFactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID
    created_by_user_id: uuid.UUID
    metric_key: str
    label: str
    value_type: str
    unit: str | None
    numeric_value: Decimal | None
    text_value: str | None
    boolean_value: bool | None
    set_value: list[str] | None
    source_kind: str
    source_method: str
    source_description: str
    source_details: dict
    site_geometry_hash: str
    site_geometry_revision: int
    source_gis_layer_id: uuid.UUID | None
    source_gis_feature_id: uuid.UUID | None
    source_feature_geometry_hash: str | None
    provenance_hash: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class ComplianceFactUseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["validated"] = "validated"
    fact: ComplianceFactResponse
    limitations: list[str]
