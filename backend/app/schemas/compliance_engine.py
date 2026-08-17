from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

ComplianceOutcome = Literal[
    "evidence_indicates_compliance",
    "evidence_indicates_non_compliance",
    "unresolved",
]

class ComplianceEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_criterion_id: uuid.UUID
    compliance_fact_id: uuid.UUID

class ComplianceEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: ComplianceOutcome
    deterministic: Literal[True] = True
    operator: str
    metric_key: str
    unit: str | None
    observed_numeric: Decimal | None = None
    threshold_numeric: Decimal | None = None
    lower_numeric: Decimal | None = None
    upper_numeric: Decimal | None = None
    observed_text: str | None = None
    expected_text: str | None = None
    observed_boolean: bool | None = None
    expected_boolean: bool | None = None
    observed_set: list[str] | None = None
    expected_values: list[str] | None = None
    policy_criterion_id: uuid.UUID
    compliance_fact_id: uuid.UUID
    limitations: list[str] = Field(default_factory=list)
