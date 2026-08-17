from __future__ import annotations
import uuid
from datetime import datetime
import numpy as np
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.temporal import TemporalMeasurement,TemporalThresholdPolicy
from app.services.raster_processing import ndvi
from app.services.rasters import get_raster,RasterError
from app.services.planning_runs import get_planning_run,save_run_state
class TemporalError(Exception): pass

def compare_ndvi_arrays(*,red_before,nir_before,red_after,nir_after,coverage_mask,threshold_policy:TemporalThresholdPolicy):
 b=ndvi(red_before,nir_before); a=ndvi(red_after,nir_after); mask=np.asarray(coverage_mask,dtype=bool)&np.isfinite(b)&np.isfinite(a)
 valid=int(mask.sum()); total=int(np.asarray(coverage_mask).size); coverage=(valid/total*100.0) if total else 0.0
 if coverage < 90.0: raise TemporalError('Usable target coverage is below the required 90% boundary.')
 delta=np.abs(a-b); changed=int(np.count_nonzero(mask & (delta>=threshold_policy.absolute_delta_threshold)))
 return {'usable_coverage_percent':coverage,'changed_pixel_count':changed,'valid_pixel_count':valid,'changed_percentage':changed/valid*100.0 if valid else 0.0,'mean_ndvi_before':float(np.nanmean(b[mask])),'mean_ndvi_after':float(np.nanmean(a[mask]))}

def validate_temporal_sources(before,after):
 if not before.provider or before.provider!=after.provider: raise TemporalError('Temporal scenes must use the same explicit provider.')
 if not before.collection or before.collection!=after.collection: raise TemporalError('Temporal scenes must use the same collection/product.')
 if not before.acquisition_datetime or not after.acquisition_datetime: raise TemporalError('Both scenes require acquisition datetime provenance.')
 if before.acquisition_datetime>=after.acquisition_datetime: raise TemporalError('Before acquisition must be earlier than after acquisition.')
 if before.crs!=after.crs: raise TemporalError('Temporal scenes must use matching CRS.')
 for required in ('B04','B08'):
  if required not in before.band_names or required not in after.band_names: raise TemporalError('Temporal NDVI requires explicit Red B04 and NIR B08 bands.')

def persist_measurement(session:Session,*,owner:User,project_id:uuid.UUID,site_id:uuid.UUID,planning_run_id:uuid.UUID,before_raster_id:uuid.UUID,after_raster_id:uuid.UUID,measurement:dict,threshold_policy:TemporalThresholdPolicy):
 before=get_raster(session,owner=owner,project_id=project_id,raster_id=before_raster_id); after=get_raster(session,owner=owner,project_id=project_id,raster_id=after_raster_id); validate_temporal_sources(before,after)
 run=get_planning_run(session,owner=owner,project_id=project_id,site_id=site_id,run_id=planning_run_id)
 m=TemporalMeasurement(project_id=project_id,site_id=site_id,planning_run_id=planning_run_id,before_raster_id=before.id,after_raster_id=after.id,provider=before.provider,collection=before.collection,before_datetime=before.acquisition_datetime,after_datetime=after.acquisition_datetime,threshold_policy=threshold_policy,**measurement,limitations=['NDVI change is a vegetation-index measurement; it does not by itself prove land-use change, construction, or causation.','Professional satellite/planning review is required for material interpretation.'])
 evidence=list(run.evidence); ids={x.get('payload',{}).get('result_id') for x in evidence if isinstance(x,dict)}
 if str(m.result_id) in ids: raise TemporalError('Duplicate temporal result identity.')
 evidence.append({'schema_version':'tool_evidence.v1','evidence_id':str(uuid.uuid4()),'project_id':str(project_id),'site_id':str(site_id),'tool_name':'satellite.temporal_ndvi','deterministic':True,'status':'measured','payload':m.model_dump(mode='json'),'sources':[{'kind':'raster_dataset','id':str(before.id),'hash':before.checksum_sha256},{'kind':'raster_dataset','id':str(after.id),'hash':after.checksum_sha256}],'limitations':m.limitations,'geometry_reference':None})
 save_run_state(session,run,evidence=evidence,status='requires_professional_review',limitations=[*run.limitations,*m.limitations]); return m
