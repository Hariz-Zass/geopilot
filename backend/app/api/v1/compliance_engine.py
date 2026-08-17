from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.compliance_engine import ComplianceEvaluationRequest, ComplianceEvaluationResponse
from app.services.compliance_engine import ComplianceEvaluationError, evaluate_compliance

router = APIRouter(prefix="/projects/{project_id}/sites/{site_id}/compliance", tags=["compliance"])

@router.post("/evaluate", response_model=ComplianceEvaluationResponse)
def evaluate(project_id: uuid.UUID, site_id: uuid.UUID, payload: ComplianceEvaluationRequest, current_user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try:
        return evaluate_compliance(session, owner=current_user, project_id=project_id, site_id=site_id, criterion_id=payload.policy_criterion_id, fact_id=payload.compliance_fact_id)
    except ComplianceEvaluationError as exc:
        raise AppError(code="compliance_evaluation_unavailable", message=str(exc), status_code=409) from exc
