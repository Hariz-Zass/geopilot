from __future__ import annotations
import uuid
from pydantic import BaseModel,Field,ConfigDict
class ReportCreate(BaseModel): planning_run_id:uuid.UUID; title:str=Field(min_length=1,max_length=255)
class ProfessionalReviewCreate(BaseModel): decision:str=Field(pattern='^(accepted|rejected|requires_changes)$'); notes:str=Field(min_length=1,max_length=10000)
class ReportResponse(BaseModel):
 model_config=ConfigDict(from_attributes=True); id:uuid.UUID; project_id:uuid.UUID; site_id:uuid.UUID; planning_run_id:uuid.UUID; title:str; status:str; report_json:dict; file_path:str|None
