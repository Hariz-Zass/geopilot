from __future__ import annotations
import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
class RasterDatasetCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=255); site_id:uuid.UUID|None=None; source_kind:Literal['upload','satellite_acquired','external_reference']; provider:str|None=None; collection:str|None=None; scene_id:str|None=None; acquisition_datetime:str|None=None; crs:str; width:int=Field(gt=0); height:int=Field(gt=0); band_names:list[str]=Field(min_length=1); pixel_size:dict; bounds:dict; nodata:dict={}; source_uri:str|None=None; checksum_sha256:str=Field(pattern=r'^[0-9a-f]{64}$'); provenance:dict={}
    @model_validator(mode='after')
    def satellite_identity(self):
        if self.source_kind=='satellite_acquired' and not all([self.provider,self.collection,self.scene_id,self.acquisition_datetime,self.source_uri]): raise ValueError('satellite_acquired requires provider, collection, scene_id, acquisition_datetime and source_uri')
        return self
class RasterDatasetResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:uuid.UUID; project_id:uuid.UUID; site_id:uuid.UUID|None; name:str; source_kind:str; provider:str|None; collection:str|None; scene_id:str|None; acquisition_datetime:str|None; crs:str; width:int; height:int; band_count:int; band_names:list; pixel_size:dict; bounds:dict; nodata:dict; source_uri:str|None; checksum_sha256:str; provenance:dict; status:str; is_archived:bool; created_at:datetime
