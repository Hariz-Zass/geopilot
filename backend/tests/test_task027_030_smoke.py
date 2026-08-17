from decimal import Decimal
from app.schemas.compliance_engine import ComplianceEvaluationResponse
from app.schemas.suitability import SuitabilityCriterionCreate

def test_compliance_evaluation_contract_is_deterministic():
 x=ComplianceEvaluationResponse(outcome='unresolved',operator='manual_review',metric_key='x',unit=None,policy_criterion_id='00000000-0000-0000-0000-000000000001',compliance_fact_id='00000000-0000-0000-0000-000000000002',limitations=[])
 assert x.deterministic is True

def test_suitability_weight_is_bounded():
 x=SuitabilityCriterionCreate(label='A',metric_key='a',factor_type='manual_review',operator='manual_review',weight=Decimal('1'),evidence_source='manual_review')
 assert x.weight==1
