from __future__ import annotations
import uuid
from decimal import Decimal
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
class SuitabilityProfileCreate(BaseModel): name:str=Field(min_length=1,max_length=160); description:str|None=None
class SuitabilityProfileResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:uuid.UUID; project_id:uuid.UUID; name:str; description:str|None; review_state:str; is_archived:bool; created_at:datetime
class SuitabilityCriterionCreate(BaseModel):
    label:str; metric_key:str; factor_type:Literal['numeric','distance','boolean','categorical','manual_review']; operator:str; weight:Decimal=Field(gt=0,le=100); threshold_numeric:Decimal|None=None; expected_value:str|None=None; evidence_source:Literal['compliance_fact','gis_feature','policy_reference','manual_review']; policy_reference_id:uuid.UUID|None=None; compliance_fact_id:uuid.UUID|None=None; gis_feature_id:uuid.UUID|None=None
class SuitabilityCriterionResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:uuid.UUID; profile_id:uuid.UUID; project_id:uuid.UUID; label:str; metric_key:str; factor_type:str; operator:str; weight:Decimal; threshold_numeric:Decimal|None; expected_value:str|None; evidence_source:str; review_state:str; created_at:datetime
class SuitabilityRunCreate(BaseModel): profile_id:uuid.UUID
class SuitabilityCriterionResultResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:uuid.UUID; criterion_id:uuid.UUID; status:str; normalized_score:Decimal|None; evidence:dict; compliance_fact_id:uuid.UUID|None; gis_feature_id:uuid.UUID|None; policy_reference_id:uuid.UUID|None
class SuitabilityRunResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:uuid.UUID; project_id:uuid.UUID; site_id:uuid.UUID; profile_id:uuid.UUID; status:str; score:Decimal|None; limitations:list; created_at:datetime; results:list[SuitabilityCriterionResultResponse]=[]
