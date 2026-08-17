from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.db import get_db_session
from app.models.user import User
from app.services.acceptance import domain_acceptance
from app.services.provider_resilience import golden_path_contract
router=APIRouter(tags=['acceptance'])
@router.get('/projects/{project_id}/sites/{site_id}/domain-acceptance')
def acceptance(project_id:uuid.UUID,site_id:uuid.UUID,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]): return domain_acceptance(session,owner=current_user,project_id=project_id,site_id=site_id)
@router.get('/system/golden-path')
def golden(): return golden_path_contract()
