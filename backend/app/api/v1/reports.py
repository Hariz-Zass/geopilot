from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.db import get_db_session
from app.models.user import User
from app.schemas.report import ReportCreate,ReportResponse,ProfessionalReviewCreate
from app.services.reports import compose_report,review_run
router=APIRouter(prefix='/projects/{project_id}/sites/{site_id}',tags=['reports-review'])
@router.post('/reports',response_model=ReportResponse,status_code=201)
def report(project_id:uuid.UUID,site_id:uuid.UUID,payload:ReportCreate,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]): return compose_report(session,owner=current_user,project_id=project_id,site_id=site_id,run_id=payload.planning_run_id,title=payload.title)
@router.post('/planning-runs/{run_id}/professional-review',status_code=201)
def review(project_id:uuid.UUID,site_id:uuid.UUID,run_id:uuid.UUID,payload:ProfessionalReviewCreate,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
 x=review_run(session,owner=current_user,project_id=project_id,site_id=site_id,run_id=run_id,decision=payload.decision,notes=payload.notes); return {'id':str(x.id),'decision':x.decision,'notes':x.notes}
