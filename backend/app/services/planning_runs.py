from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.planning_run import PlanningRun
from app.models.user import User
from app.schemas.planning_run import PlanningRunCreate
from app.services.isolation import SiteState, resolve_analysis_scope
class PlanningRunError(Exception): pass

def create_planning_run(session:Session,*,owner:User,project_id:uuid.UUID,site_id:uuid.UUID,request:PlanningRunCreate,site_state:SiteState=SiteState.ACTIVE):
 resolve_analysis_scope(session,owner=owner,project_id=project_id,site_id=site_id,site_state=site_state)
 r=PlanningRun(project_id=project_id,site_id=site_id,created_by_user_id=owner.id,question=request.question.strip(),development_intent=request.development_intent,status='created',plan=[],evidence=[],findings=[],limitations=[],provider_metadata={},review_state='unreviewed'); session.add(r); session.commit(); session.refresh(r); return r

def get_planning_run(session:Session,*,owner:User,project_id:uuid.UUID,site_id:uuid.UUID,run_id:uuid.UUID,site_state:SiteState=SiteState.ACTIVE):
 resolve_analysis_scope(session,owner=owner,project_id=project_id,site_id=site_id,site_state=site_state)
 r=session.scalar(select(PlanningRun).where(PlanningRun.id==run_id,PlanningRun.project_id==project_id,PlanningRun.site_id==site_id))
 if not r: raise PlanningRunError('PlanningRun not found.')
 return r

def save_run_state(session:Session,run:PlanningRun,*,status=None,plan=None,evidence=None,findings=None,limitations=None,provider_metadata=None,synthesis=None):
 if status is not None: run.status=status
 if plan is not None: run.plan=plan
 if evidence is not None: run.evidence=evidence
 if findings is not None: run.findings=findings
 if limitations is not None: run.limitations=limitations
 if provider_metadata is not None: run.provider_metadata=provider_metadata
 if synthesis is not None: run.synthesis=synthesis
 session.commit(); session.refresh(run); return run
