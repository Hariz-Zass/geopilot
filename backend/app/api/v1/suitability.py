from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import APIRouter,Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.models.suitability import SuitabilityProfile,SuitabilityCriterion
from app.schemas.suitability import *
from app.services.suitability import create_profile,create_criterion,execute_run,SuitabilityError
router=APIRouter(prefix='/projects/{project_id}',tags=['suitability'])
@router.post('/suitability-profiles',response_model=SuitabilityProfileResponse,status_code=201)
def profile(project_id:uuid.UUID,payload:SuitabilityProfileCreate,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]): return create_profile(session,owner=current_user,project_id=project_id,request=payload)
@router.post('/suitability-profiles/{profile_id}/criteria',response_model=SuitabilityCriterionResponse,status_code=201)
def criterion(project_id:uuid.UUID,profile_id:uuid.UUID,payload:SuitabilityCriterionCreate,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return create_criterion(session,owner=current_user,project_id=project_id,profile_id=profile_id,request=payload)
    except SuitabilityError as exc: raise AppError(code='suitability_configuration_invalid',message=str(exc),status_code=409) from exc
@router.post('/sites/{site_id}/suitability-runs',response_model=SuitabilityRunResponse,status_code=201)
def run(project_id:uuid.UUID,site_id:uuid.UUID,payload:SuitabilityRunCreate,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:r,results=execute_run(session,owner=current_user,project_id=project_id,site_id=site_id,profile_id=payload.profile_id); return SuitabilityRunResponse.model_validate(r).model_copy(update={'results':[SuitabilityCriterionResultResponse.model_validate(x) for x in results]})
    except SuitabilityError as exc: raise AppError(code='suitability_configuration_invalid',message=str(exc),status_code=409) from exc
