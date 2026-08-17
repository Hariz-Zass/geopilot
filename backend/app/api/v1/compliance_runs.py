from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.db import get_db_session
from app.models.user import User
from app.schemas.compliance_run import ComplianceRunCreateRequest, ComplianceRunResponse, ComplianceFindingResponse
from app.services.compliance_runs import execute_compliance_run, list_compliance_runs, findings_for_run
router=APIRouter(prefix='/projects/{project_id}/sites/{site_id}/compliance-runs',tags=['compliance-runs'])
@router.post('',response_model=ComplianceRunResponse,status_code=201)
def create(project_id:uuid.UUID,site_id:uuid.UUID,payload:ComplianceRunCreateRequest,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    run,findings=execute_compliance_run(session,owner=current_user,project_id=project_id,site_id=site_id,criterion_id=payload.policy_criterion_id,fact_id=payload.compliance_fact_id)
    return ComplianceRunResponse.model_validate(run).model_copy(update={'findings':[ComplianceFindingResponse.model_validate(x) for x in findings]})
@router.get('',response_model=list[ComplianceRunResponse])
def listing(project_id:uuid.UUID,site_id:uuid.UUID,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    out=[]
    for run in list_compliance_runs(session,owner=current_user,project_id=project_id,site_id=site_id): out.append(ComplianceRunResponse.model_validate(run).model_copy(update={'findings':[ComplianceFindingResponse.model_validate(x) for x in findings_for_run(session,run.id)]}))
    return out
