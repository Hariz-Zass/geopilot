from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ValueType = Literal["numeric", "text", "boolean", "set", "manual_review"]
Operator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "not_in", "bool_eq", "manual_review"]
CriterionReviewAction = Literal["verify", "reject", "requires_review"]


class PolicyCriterionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_reference_id: uuid.UUID
    code: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    label: str = Field(min_length=1, max_length=255)
    metric_key: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9_.:-]*$")
    value_type: ValueType
    operator: Operator
    unit: str | None = Field(default=None, max_length=80)
    threshold_numeric: Decimal | None = None
    lower_numeric: Decimal | None = None
    upper_numeric: Decimal | None = None
    expected_text: str | None = Field(default=None, max_length=2000)
    expected_boolean: bool | None = None
    expected_values: list[str] | None = Field(default=None, min_length=1, max_length=100)
    source_evidence_text: str = Field(min_length=1, max_length=6000)
    interpretation_notes: str | None = Field(default=None, max_length=6000)
    applicability_notes: str | None = Field(default=None, max_length=6000)

    @model_validator(mode="after")
    def validate_rule_shape(self):
        numeric_ops = {"eq", "ne", "gt", "gte", "lt", "lte"}
        if self.value_type == "numeric":
            if self.operator not in numeric_ops | {"between"}:
                raise ValueError("numeric criterion uses an invalid operator")
            if self.operator == "between":
                if self.lower_numeric is None or self.upper_numeric is None:
                    raise ValueError("between criterion requires lower_numeric and upper_numeric")
                if self.lower_numeric > self.upper_numeric:
                    raise ValueError("lower_numeric must be <= upper_numeric")
                if self.threshold_numeric is not None:
                    raise ValueError("between criterion may not set threshold_numeric")
            else:
                if self.threshold_numeric is None:
                    raise ValueError("numeric criterion requires threshold_numeric")
                if self.lower_numeric is not None or self.upper_numeric is not None:
                    raise ValueError("non-between numeric criterion may not set lower/upper bounds")
        elif self.value_type == "text":
            if self.operator not in {"eq", "ne"} or not self.expected_text:
                raise ValueError("text criterion requires eq/ne and expected_text")
        elif self.value_type == "set":
            if self.operator not in {"in", "not_in"} or not self.expected_values:
                raise ValueError("set criterion requires in/not_in and expected_values")
            values = [v.strip() for v in self.expected_values if v.strip()]
            if not values or len(values) != len(set(v.casefold() for v in values)):
                raise ValueError("expected_values must be non-empty and unique")
            self.expected_values = values
        elif self.value_type == "boolean":
            if self.operator != "bool_eq" or self.expected_boolean is None:
                raise ValueError("boolean criterion requires bool_eq and expected_boolean")
        else:
            if self.operator != "manual_review":
                raise ValueError("manual_review value type requires manual_review operator")
        return self


class PolicyCriterionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=255)
    interpretation_notes: str | None = Field(default=None, max_length=6000)
    applicability_notes: str | None = Field(default=None, max_length=6000)
    is_archived: bool | None = None


class PolicyCriterionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: CriterionReviewAction
    review_notes: str | None = Field(default=None, max_length=6000)


class PolicyCriterionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    project_id: uuid.UUID
    policy_reference_id: uuid.UUID
    created_by_user_id: uuid.UUID
    reviewed_by_user_id: uuid.UUID | None
    code: str
    label: str
    metric_key: str
    value_type: str
    operator: str
    unit: str | None
    threshold_numeric: Decimal | None
    lower_numeric: Decimal | None
    upper_numeric: Decimal | None
    expected_text: str | None
    expected_boolean: bool | None
    expected_values: list[str] | None
    source_evidence_text: str
    interpretation_notes: str | None
    applicability_notes: str | None
    review_notes: str | None
    representation_state: str
    review_state: str
    is_archived: bool
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PolicyCriterionUseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["validated"] = "validated"
    criterion: PolicyCriterionResponse
    policy_reference_id: uuid.UUID
    limitations: list[str]
