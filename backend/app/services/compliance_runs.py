from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.compliance_run import ComplianceRun, ComplianceFinding
from app.schemas.compliance_engine import ComplianceEvaluationResponse
from app.services.compliance_engine import evaluate_compliance
from app.services.isolation import resolve_analysis_scope

def execute_compliance_run(session: Session, *, owner: User, project_id: uuid.UUID, site_id: uuid.UUID, criterion_id: uuid.UUID, fact_id: uuid.UUID):
    resolve_analysis_scope(session,owner=owner,project_id=project_id,site_id=site_id)
    result=evaluate_compliance(session,owner=owner,project_id=project_id,site_id=site_id,criterion_id=criterion_id,fact_id=fact_id)
    run=ComplianceRun(project_id=project_id,site_id=site_id,created_by_user_id=owner.id,status='unresolved' if result.outcome=='unresolved' else 'completed',deterministic=True,limitations=result.limitations)
    session.add(run); session.flush()
    finding=ComplianceFinding(run_id=run.id,project_id=project_id,site_id=site_id,policy_criterion_id=criterion_id,compliance_fact_id=fact_id,outcome=result.outcome,evaluation=result.model_dump(mode='json'))
    session.add(finding); session.commit(); session.refresh(run); session.refresh(finding); return run,[finding]

def list_compliance_runs(session: Session, *, owner: User, project_id: uuid.UUID, site_id: uuid.UUID):
    resolve_analysis_scope(session,owner=owner,project_id=project_id,site_id=site_id)
    return list(session.scalars(select(ComplianceRun).where(ComplianceRun.project_id==project_id,ComplianceRun.site_id==site_id).order_by(ComplianceRun.created_at.desc())))

def findings_for_run(session: Session, run_id): return list(session.scalars(select(ComplianceFinding).where(ComplianceFinding.run_id==run_id)))
