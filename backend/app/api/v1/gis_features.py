from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.gis_feature import GISFeatureCollectionRequest, GISFeatureCollectionResponse, GISFeatureCreateRequest, GISFeatureResponse
from app.services.gis_features import *
from app.services.gis_layers import GISLayerNotFoundError, GISLayerProjectNotFoundError

router=APIRouter(prefix="/projects/{project_id}/gis-layers/{layer_id}/features", tags=["gis-features"])

def _err(exc: Exception) -> AppError:
    if isinstance(exc, GISLayerProjectNotFoundError): return AppError(code="project_not_found",message="Project not found.",status_code=404)
    if isinstance(exc, GISLayerNotFoundError): return AppError(code="gis_layer_not_found",message="GIS layer not found.",status_code=404)
    if isinstance(exc, GISFeatureNotFoundError): return AppError(code="gis_feature_not_found",message="GIS feature not found.",status_code=404)
    return AppError(code="gis_feature_state_invalid",message=str(exc) or "GIS feature state is invalid.",status_code=409)

def _response(feature): return GISFeatureResponse.model_validate(serialize_feature(feature))

@router.post("",response_model=GISFeatureResponse,status_code=201)
def create(project_id:uuid.UUID,layer_id:uuid.UUID,payload:GISFeatureCreateRequest,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try: f=create_gis_feature(session,owner=current_user,project_id=project_id,layer_id=layer_id,request=payload)
    except (GISLayerProjectNotFoundError,GISLayerNotFoundError,GISFeatureStateError) as exc: raise _err(exc) from exc
    return _response(f)

@router.post("/ingest",response_model=GISFeatureCollectionResponse,status_code=201)
def ingest(project_id:uuid.UUID,layer_id:uuid.UUID,payload:GISFeatureCollectionRequest,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try: features=ingest_feature_collection(session,owner=current_user,project_id=project_id,layer_id=layer_id,request=payload)
    except (GISLayerProjectNotFoundError,GISLayerNotFoundError,GISFeatureStateError) as exc: raise _err(exc) from exc
    items=[_response(x) for x in features]; return GISFeatureCollectionResponse(count=len(items),features=items)

@router.get("",response_model=list[GISFeatureResponse])
def list_owned(project_id:uuid.UUID,layer_id:uuid.UUID,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)],include_archived:Annotated[bool,Query()]=False):
    try: fs=list_gis_features(session,owner=current_user,project_id=project_id,layer_id=layer_id,include_archived=include_archived)
    except (GISLayerProjectNotFoundError,GISLayerNotFoundError) as exc: raise _err(exc) from exc
    return [_response(x) for x in fs]

@router.get("/{feature_id}",response_model=GISFeatureResponse)
def get_one(project_id:uuid.UUID,layer_id:uuid.UUID,feature_id:uuid.UUID,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try: f=get_gis_feature(session,owner=current_user,project_id=project_id,layer_id=layer_id,feature_id=feature_id)
    except (GISLayerProjectNotFoundError,GISLayerNotFoundError,GISFeatureNotFoundError) as exc: raise _err(exc) from exc
    return _response(f)

@router.patch("/{feature_id}/archive",response_model=GISFeatureResponse)
def archive(project_id:uuid.UUID,layer_id:uuid.UUID,feature_id:uuid.UUID,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try: f=archive_gis_feature(session,owner=current_user,project_id=project_id,layer_id=layer_id,feature_id=feature_id)
    except (GISLayerProjectNotFoundError,GISLayerNotFoundError,GISFeatureNotFoundError) as exc: raise _err(exc) from exc
    return _response(f)

@router.delete("/{feature_id}",status_code=204)
def delete(project_id:uuid.UUID,layer_id:uuid.UUID,feature_id:uuid.UUID,current_user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try: delete_gis_feature(session,owner=current_user,project_id=project_id,layer_id=layer_id,feature_id=feature_id)
    except (GISLayerProjectNotFoundError,GISLayerNotFoundError,GISFeatureNotFoundError) as exc: raise _err(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
