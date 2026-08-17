from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.gis_layer import GISLayerCreateRequest, GISLayerResponse, GISLayerUpdateRequest
from app.services.gis_layers import *

router = APIRouter(prefix="/projects/{project_id}/gis-layers", tags=["gis-layers"])

def _translate(exc: Exception) -> AppError:
    if isinstance(exc, GISLayerProjectNotFoundError): return AppError(code="project_not_found", message="Project not found.", status_code=404)
    if isinstance(exc, GISLayerNotFoundError): return AppError(code="gis_layer_not_found", message="GIS layer not found.", status_code=404)
    return AppError(code="gis_layer_state_invalid", message=str(exc) or "GIS layer state is invalid.", status_code=409)

@router.post("", response_model=GISLayerResponse, status_code=201)
def create(project_id: uuid.UUID, payload: GISLayerCreateRequest, current_user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try: layer=create_gis_layer(session, owner=current_user, project_id=project_id, request=payload)
    except (GISLayerProjectNotFoundError, GISLayerStateError) as exc: raise _translate(exc) from exc
    return GISLayerResponse.model_validate(layer)

@router.get("", response_model=list[GISLayerResponse])
def list_owned(project_id: uuid.UUID, current_user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)], include_archived: Annotated[bool, Query()]=False):
    try: layers=list_gis_layers(session, owner=current_user, project_id=project_id, include_archived=include_archived)
    except GISLayerProjectNotFoundError as exc: raise _translate(exc) from exc
    return [GISLayerResponse.model_validate(x) for x in layers]

@router.get("/{layer_id}", response_model=GISLayerResponse)
def get_one(project_id: uuid.UUID, layer_id: uuid.UUID, current_user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try: layer=get_gis_layer(session, owner=current_user, project_id=project_id, layer_id=layer_id)
    except (GISLayerProjectNotFoundError, GISLayerNotFoundError) as exc: raise _translate(exc) from exc
    return GISLayerResponse.model_validate(layer)

@router.patch("/{layer_id}", response_model=GISLayerResponse)
def update(project_id: uuid.UUID, layer_id: uuid.UUID, payload: GISLayerUpdateRequest, current_user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try: layer=update_gis_layer(session, owner=current_user, project_id=project_id, layer_id=layer_id, request=payload)
    except (GISLayerProjectNotFoundError, GISLayerNotFoundError, GISLayerStateError) as exc: raise _translate(exc) from exc
    return GISLayerResponse.model_validate(layer)

@router.delete("/{layer_id}", status_code=204)
def delete(project_id: uuid.UUID, layer_id: uuid.UUID, current_user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try: delete_gis_layer(session, owner=current_user, project_id=project_id, layer_id=layer_id)
    except (GISLayerProjectNotFoundError, GISLayerNotFoundError) as exc: raise _translate(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
