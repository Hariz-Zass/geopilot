from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.schemas.compliance_engine import ComplianceEvaluationRequest
class ComplianceRunCreateRequest(ComplianceEvaluationRequest): pass
class ComplianceFindingResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: uuid.UUID; run_id: uuid.UUID; project_id: uuid.UUID; site_id: uuid.UUID; policy_criterion_id: uuid.UUID; compliance_fact_id: uuid.UUID; outcome: str; evaluation: dict; created_at: datetime
class ComplianceRunResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: uuid.UUID; project_id: uuid.UUID; site_id: uuid.UUID; created_by_user_id: uuid.UUID; status: str; deterministic: bool; limitations: list; created_at: datetime; findings: list[ComplianceFindingResponse]=[]
