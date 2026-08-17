from __future__ import annotations
import uuid
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
class EvidenceSourceRef(BaseModel):
    model_config=ConfigDict(extra='forbid'); kind:Literal['document_chunk','policy_reference','compliance_fact','compliance_finding','suitability_result','gis_feature','raster_dataset','temporal_measurement','user_input']; id:uuid.UUID|str; hash:str|None=None
class ToolEvidence(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version:Literal['tool_evidence.v1']='tool_evidence.v1'; evidence_id:uuid.UUID=Field(default_factory=uuid.uuid4); project_id:uuid.UUID; site_id:uuid.UUID|None=None; tool_name:str; deterministic:bool; status:Literal['measured','evaluated','retrieved','unresolved','degraded']; payload:dict; sources:list[EvidenceSourceRef]=Field(default_factory=list); limitations:list[str]=Field(default_factory=list); geometry_reference:dict|None=None
    @model_validator(mode='after')
    def authority(self):
        if self.status in {'measured','evaluated'} and not self.deterministic: raise ValueError('measured/evaluated evidence must be deterministic')
        if not self.sources and self.status not in {'unresolved','degraded'}: raise ValueError('authoritative evidence requires at least one source identity')
        return self
