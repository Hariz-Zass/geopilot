from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.compliance_run import ComplianceRun,ComplianceFinding
from app.models.suitability import SuitabilityAnalysisRun,SuitabilityCriterionResult
from app.services.isolation import resolve_analysis_scope

def domain_acceptance(session:Session,*,owner:User,project_id:uuid.UUID,site_id:uuid.UUID)->dict:
 resolve_analysis_scope(session,owner=owner,project_id=project_id,site_id=site_id)
 cr=session.scalar(select(ComplianceRun).where(ComplianceRun.project_id==project_id,ComplianceRun.site_id==site_id).order_by(ComplianceRun.created_at.desc()))
 compliance_ok=False
 if cr:
  finding=session.scalar(select(ComplianceFinding).where(ComplianceFinding.run_id==cr.id))
  compliance_ok=bool(finding and finding.outcome in {'evidence_indicates_compliance','evidence_indicates_non_compliance'})
 sr=session.scalar(select(SuitabilityAnalysisRun).where(SuitabilityAnalysisRun.project_id==project_id,SuitabilityAnalysisRun.site_id==site_id).order_by(SuitabilityAnalysisRun.created_at.desc()))
 suitability_ok=False
 if sr:
  results=list(session.scalars(select(SuitabilityCriterionResult).where(SuitabilityCriterionResult.run_id==sr.id)))
  suitability_ok=bool(results) and all(r.status=='evaluated' and r.normalized_score is not None for r in results)
 return {'compliance_real_data_accepted':compliance_ok,'suitability_real_data_accepted':suitability_ok,'overall':'accepted' if compliance_ok and suitability_ok else 'incomplete','limitations':([] if compliance_ok else ['No accepted deterministic Compliance finding exists.'])+([] if suitability_ok else ['No fully evaluated legitimate Suitability run exists; thresholds/evidence must not be fabricated.'])}
