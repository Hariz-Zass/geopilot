from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel,ConfigDict,Field,model_validator
class TemporalThresholdPolicy(BaseModel):
    version:str='ndvi-change-v1'; absolute_delta_threshold:float=Field(default=0.2,gt=0,le=2)
class TemporalMeasureRequest(BaseModel):
    model_config=ConfigDict(extra='forbid'); planning_run_id:uuid.UUID; before_raster_id:uuid.UUID; after_raster_id:uuid.UUID; threshold_policy:TemporalThresholdPolicy=TemporalThresholdPolicy()
    @model_validator(mode='after')
    def distinct(self):
        if self.before_raster_id==self.after_raster_id: raise ValueError('before and after raster IDs must be distinct')
        return self
class TemporalMeasurement(BaseModel):
    schema_version:str='temporal_measurement.v1'; result_id:uuid.UUID=Field(default_factory=uuid.uuid4); project_id:uuid.UUID; site_id:uuid.UUID; planning_run_id:uuid.UUID; before_raster_id:uuid.UUID; after_raster_id:uuid.UUID; provider:str; collection:str; before_datetime:str; after_datetime:str; threshold_policy:TemporalThresholdPolicy; usable_coverage_percent:float; changed_pixel_count:int; valid_pixel_count:int; changed_percentage:float; mean_ndvi_before:float; mean_ndvi_after:float; deterministic:bool=True; method:str='ndvi-red-nir-v1'; limitations:list[str]=[]
