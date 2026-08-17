from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel,ConfigDict,Field
class PlanningRunCreate(BaseModel): question:str=Field(min_length=3,max_length=6000); development_intent:str|None=Field(default=None,max_length=6000)
class PlanningRunResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:uuid.UUID; project_id:uuid.UUID; site_id:uuid.UUID; created_by_user_id:uuid.UUID; question:str; development_intent:str|None; status:str; plan:list; evidence:list; findings:list; limitations:list; provider_metadata:dict; synthesis:str|None; review_state:str; created_at:datetime; updated_at:datetime
