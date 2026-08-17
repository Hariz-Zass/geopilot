from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gis_layer import GISLayer
from app.models.user import User
from app.schemas.gis_layer import GISLayerCreateRequest, GISLayerUpdateRequest
from app.services.isolation import ProjectScopeNotFoundError, ProjectState, ScopeStateError, resolve_project_scope


class GISLayerNotFoundError(Exception): pass
class GISLayerProjectNotFoundError(Exception): pass
class GISLayerStateError(Exception): pass


def _project(session: Session, *, owner: User, project_id: uuid.UUID, active: bool = False):
    try:
        return resolve_project_scope(
            session, owner=owner, project_id=project_id,
            state=ProjectState.ACTIVE if active else ProjectState.ANY,
        ).project
    except ProjectScopeNotFoundError as exc:
        raise GISLayerProjectNotFoundError from exc
    except ScopeStateError as exc:
        raise GISLayerStateError(str(exc)) from exc


def create_gis_layer(session: Session, *, owner: User, project_id: uuid.UUID, request: GISLayerCreateRequest) -> GISLayer:
    project = _project(session, owner=owner, project_id=project_id, active=True)
    layer = GISLayer(project_id=project.id, **request.model_dump())
    session.add(layer); session.commit(); session.refresh(layer); return layer


def list_gis_layers(session: Session, *, owner: User, project_id: uuid.UUID, include_archived: bool = False) -> list[GISLayer]:
    project = _project(session, owner=owner, project_id=project_id)
    stmt = select(GISLayer).where(GISLayer.project_id == project.id)
    if not include_archived: stmt = stmt.where(GISLayer.is_archived.is_(False))
    return list(session.scalars(stmt.order_by(GISLayer.created_at.desc(), GISLayer.id.desc())))


def get_gis_layer(session: Session, *, owner: User, project_id: uuid.UUID, layer_id: uuid.UUID) -> GISLayer:
    project = _project(session, owner=owner, project_id=project_id)
    layer = session.scalar(select(GISLayer).where(GISLayer.id == layer_id, GISLayer.project_id == project.id))
    if layer is None: raise GISLayerNotFoundError
    return layer


def update_gis_layer(session: Session, *, owner: User, project_id: uuid.UUID, layer_id: uuid.UUID, request: GISLayerUpdateRequest) -> GISLayer:
    layer = get_gis_layer(session, owner=owner, project_id=project_id, layer_id=layer_id)
    changes = request.model_dump(exclude_unset=True)
    if changes.get("is_archived") is True: changes["is_active"] = False
    if changes.get("is_active") is True and layer.is_archived and changes.get("is_archived") is not False:
        raise GISLayerStateError("archived GIS layer must be restored before activation")
    for key, value in changes.items(): setattr(layer, key, value)
    session.commit(); session.refresh(layer); return layer


def delete_gis_layer(session: Session, *, owner: User, project_id: uuid.UUID, layer_id: uuid.UUID) -> None:
    layer = get_gis_layer(session, owner=owner, project_id=project_id, layer_id=layer_id)
    session.delete(layer); session.commit()
