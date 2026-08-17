from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.db import get_db_session
from app.models.user import User
from app.schemas.planning_run import PlanningRunCreate,PlanningRunResponse
from app.services.planning_runs import create_planning_run,get_planning_run
from app.services.planning_orchestrator import execute_planning_run
router=APIRouter(prefix='/projects/{project_id}/sites/{site_id}/planning-runs',tags=['planning-runs'])
@router.post('',response_model=PlanningRunResponse,status_code=201)
def create(project_id:uuid.UUID,site_id:uuid.UUID,payload:PlanningRunCreate,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]): return create_planning_run(session,owner=current_user,project_id=project_id,site_id=site_id,request=payload)
@router.get('/{run_id}',response_model=PlanningRunResponse)
def get(project_id:uuid.UUID,site_id:uuid.UUID,run_id:uuid.UUID,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]): return get_planning_run(session,owner=current_user,project_id=project_id,site_id=site_id,run_id=run_id)
@router.post('/{run_id}/execute',response_model=PlanningRunResponse)
def execute(project_id:uuid.UUID,site_id:uuid.UUID,run_id:uuid.UUID,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]): return execute_planning_run(session,owner=current_user,project_id=project_id,site_id=site_id,run_id=run_id)
