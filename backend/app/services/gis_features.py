from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gis_feature import GISFeature
from app.models.gis_layer import GISLayer
from app.models.user import User
from app.schemas.gis_feature import GISFeatureCollectionRequest, GISFeatureCreateRequest, GISFeatureInput, geometry_digest, geometry_to_ewkt, ewkt_to_geometry
from app.services.gis_layers import GISLayerNotFoundError, GISLayerProjectNotFoundError, get_gis_layer


class GISFeatureNotFoundError(Exception): pass
class GISFeatureStateError(Exception): pass


def _layer(session: Session, *, owner: User, project_id: uuid.UUID, layer_id: uuid.UUID, writable: bool = False) -> GISLayer:
    layer=get_gis_layer(session, owner=owner, project_id=project_id, layer_id=layer_id)
    if writable and (layer.is_archived or not layer.is_active):
        raise GISFeatureStateError("GIS features may only be ingested into an active, non-archived GIS layer")
    return layer


def _ensure_type(layer: GISLayer, feature_type: str) -> None:
    declared=layer.geometry_type
    if declared in {None, "Unknown"}:
        layer.geometry_type=feature_type
    elif declared != feature_type:
        if declared == "Mixed": return
        raise GISFeatureStateError(f"feature geometry type {feature_type} does not match layer geometry_type {declared}")


def _build(layer: GISLayer, request: GISFeatureCreateRequest) -> GISFeature:
    _ensure_type(layer, request.geometry.type)
    return GISFeature(
        project_id=layer.project_id, layer_id=layer.id,
        source_feature_id=request.source_feature_id,
        geometry=geometry_to_ewkt(request.geometry), geometry_type=request.geometry.type,
        geometry_hash=geometry_digest(request.geometry), properties=request.properties,
    )


def create_gis_feature(session: Session, *, owner: User, project_id: uuid.UUID, layer_id: uuid.UUID, request: GISFeatureCreateRequest) -> GISFeature:
    layer=_layer(session, owner=owner, project_id=project_id, layer_id=layer_id, writable=True)
    feature=_build(layer, request); session.add(feature); session.commit(); session.refresh(feature); return feature


def ingest_feature_collection(session: Session, *, owner: User, project_id: uuid.UUID, layer_id: uuid.UUID, request: GISFeatureCollectionRequest) -> list[GISFeature]:
    layer=_layer(session, owner=owner, project_id=project_id, layer_id=layer_id, writable=True)
    built=[]
    try:
        for item in request.features:
            source_id=None if item.id is None else str(item.id)
            built.append(_build(layer, GISFeatureCreateRequest(source_feature_id=source_id, geometry=item.geometry, properties=item.properties)))
        session.add_all(built); session.commit()
    except Exception:
        session.rollback(); raise
    for feature in built: session.refresh(feature)
    return built


def list_gis_features(session: Session, *, owner: User, project_id: uuid.UUID, layer_id: uuid.UUID, include_archived: bool = False) -> list[GISFeature]:
    layer=_layer(session, owner=owner, project_id=project_id, layer_id=layer_id)
    stmt=select(GISFeature).where(GISFeature.project_id==project_id, GISFeature.layer_id==layer.id)
    if not include_archived: stmt=stmt.where(GISFeature.is_archived.is_(False))
    return list(session.scalars(stmt.order_by(GISFeature.created_at.asc(), GISFeature.id.asc())))


def get_gis_feature(session: Session, *, owner: User, project_id: uuid.UUID, layer_id: uuid.UUID, feature_id: uuid.UUID) -> GISFeature:
    layer=_layer(session, owner=owner, project_id=project_id, layer_id=layer_id)
    feature=session.scalar(select(GISFeature).where(GISFeature.id==feature_id, GISFeature.project_id==project_id, GISFeature.layer_id==layer.id))
    if feature is None: raise GISFeatureNotFoundError
    return feature


def archive_gis_feature(session: Session, *, owner: User, project_id: uuid.UUID, layer_id: uuid.UUID, feature_id: uuid.UUID) -> GISFeature:
    feature=get_gis_feature(session, owner=owner, project_id=project_id, layer_id=layer_id, feature_id=feature_id)
    feature.is_archived=True; session.commit(); session.refresh(feature); return feature


def delete_gis_feature(session: Session, *, owner: User, project_id: uuid.UUID, layer_id: uuid.UUID, feature_id: uuid.UUID) -> None:
    feature=get_gis_feature(session, owner=owner, project_id=project_id, layer_id=layer_id, feature_id=feature_id)
    session.delete(feature); session.commit()


def serialize_feature(feature: GISFeature) -> dict:
    return {
        "id":feature.id,"project_id":feature.project_id,"layer_id":feature.layer_id,
        "source_feature_id":feature.source_feature_id,"geometry":ewkt_to_geometry(feature.geometry),
        "geometry_type":feature.geometry_type,"geometry_hash":feature.geometry_hash,"properties":feature.properties,
        "is_archived":feature.is_archived,"created_at":feature.created_at,"updated_at":feature.updated_at,
    }
