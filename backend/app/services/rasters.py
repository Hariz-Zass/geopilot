from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.raster import RasterDataset
from app.models.user import User
from app.schemas.raster import RasterDatasetCreate
from app.services.isolation import resolve_project_scope,resolve_site_scope,ProjectState,SiteState
class RasterError(Exception): pass

def create_raster(session:Session,*,owner:User,project_id:uuid.UUID,request:RasterDatasetCreate):
    resolve_project_scope(session,owner=owner,project_id=project_id,state=ProjectState.ACTIVE)
    if request.site_id: resolve_site_scope(session,owner=owner,project_id=project_id,site_id=request.site_id,project_state=ProjectState.ACTIVE,site_state=SiteState.AVAILABLE)
    x=RasterDataset(project_id=project_id,created_by_user_id=owner.id,band_count=len(request.band_names),status='ready',is_archived=False,**request.model_dump()); session.add(x); session.commit(); session.refresh(x); return x

def get_raster(session:Session,*,owner:User,project_id:uuid.UUID,raster_id:uuid.UUID,require_ready=True):
    resolve_project_scope(session,owner=owner,project_id=project_id,state=ProjectState.ACTIVE)
    x=session.scalar(select(RasterDataset).where(RasterDataset.id==raster_id,RasterDataset.project_id==project_id))
    if not x or x.is_archived: raise RasterError('RasterDataset not found or archived.')
    if require_ready and x.status!='ready': raise RasterError('RasterDataset is not ready.')
    return x
