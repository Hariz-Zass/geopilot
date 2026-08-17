from __future__ import annotations
import uuid
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.suitability import SuitabilityProfile,SuitabilityCriterion,SuitabilityAnalysisRun,SuitabilityCriterionResult
from app.schemas.suitability import SuitabilityProfileCreate,SuitabilityCriterionCreate
from app.services.isolation import resolve_analysis_scope, resolve_project_scope, ProjectState
from app.services.compliance_facts import resolve_compliance_fact_for_use

class SuitabilityError(Exception): pass

def create_profile(session:Session,*,owner:User,project_id:uuid.UUID,request:SuitabilityProfileCreate):
    resolve_project_scope(session,owner=owner,project_id=project_id,state=ProjectState.ACTIVE)
    x=SuitabilityProfile(project_id=project_id,created_by_user_id=owner.id,name=request.name.strip(),description=request.description,review_state='unreviewed',is_archived=False); session.add(x); session.commit(); session.refresh(x); return x

def create_criterion(session:Session,*,owner:User,project_id:uuid.UUID,profile_id:uuid.UUID,request:SuitabilityCriterionCreate):
    resolve_project_scope(session,owner=owner,project_id=project_id,state=ProjectState.ACTIVE)
    p=session.scalar(select(SuitabilityProfile).where(SuitabilityProfile.id==profile_id,SuitabilityProfile.project_id==project_id,SuitabilityProfile.is_archived.is_(False)))
    if not p: raise SuitabilityError('SuitabilityProfile not found.')
    # No invented thresholds: numeric/distance factors require durable evidence source and explicit threshold.
    if request.factor_type in {'numeric','distance'} and request.threshold_numeric is None: raise SuitabilityError('Numeric/distance suitability criteria require an explicit reviewed threshold.')
    source_ids=[request.compliance_fact_id,request.gis_feature_id,request.policy_reference_id]
    if request.evidence_source!='manual_review' and sum(v is not None for v in source_ids)!=1: raise SuitabilityError('Exactly one durable evidence lineage ID is required.')
    x=SuitabilityCriterion(profile_id=profile_id,project_id=project_id,review_state='verified',**request.model_dump()); session.add(x); session.commit(); session.refresh(x); return x

def execute_run(session:Session,*,owner:User,project_id:uuid.UUID,site_id:uuid.UUID,profile_id:uuid.UUID):
    resolve_analysis_scope(session,owner=owner,project_id=project_id,site_id=site_id)
    p=session.scalar(select(SuitabilityProfile).where(SuitabilityProfile.id==profile_id,SuitabilityProfile.project_id==project_id,SuitabilityProfile.is_archived.is_(False)))
    if not p: raise SuitabilityError('SuitabilityProfile not found.')
    criteria=list(session.scalars(select(SuitabilityCriterion).where(SuitabilityCriterion.profile_id==profile_id,SuitabilityCriterion.review_state=='verified')))
    if not criteria: raise SuitabilityError('No verified SuitabilityCriterion exists; thresholds must not be fabricated.')
    run=SuitabilityAnalysisRun(project_id=project_id,site_id=site_id,profile_id=profile_id,status='completed',score=None,limitations=[],created_by_user_id=owner.id); session.add(run); session.flush()
    scores=[]; unresolved=False; results=[]
    for c in criteria:
        status='requires_professional_review'; score=None; evidence={'evidence_source':c.evidence_source}
        if c.evidence_source=='compliance_fact' and c.compliance_fact_id:
            fact,_=resolve_compliance_fact_for_use(session,owner=owner,project_id=project_id,site_id=site_id,fact_id=c.compliance_fact_id)
            evidence.update({'metric_key':fact.metric_key,'numeric_value':str(fact.numeric_value) if fact.numeric_value is not None else None})
            if c.factor_type in {'numeric','distance'} and fact.numeric_value is not None and c.threshold_numeric is not None:
                ok = fact.numeric_value >= c.threshold_numeric if c.operator in {'gte','gt'} else fact.numeric_value <= c.threshold_numeric if c.operator in {'lte','lt'} else fact.numeric_value==c.threshold_numeric
                score=Decimal('1') if ok else Decimal('0'); status='evaluated'; scores.append((score,c.weight))
            else: unresolved=True
        else: unresolved=True
        r=SuitabilityCriterionResult(run_id=run.id,criterion_id=c.id,status=status,normalized_score=score,evidence=evidence,compliance_fact_id=c.compliance_fact_id,gis_feature_id=c.gis_feature_id,policy_reference_id=c.policy_reference_id); session.add(r); results.append(r)
    if scores:
        total=sum(w for _,w in scores); run.score=sum(s*w for s,w in scores)/total
    if unresolved: run.status='requires_professional_review'; run.limitations=['One or more suitability criteria require professional review or unsupported evidence resolution.']
    session.commit(); session.refresh(run); [session.refresh(r) for r in results]; return run,results
