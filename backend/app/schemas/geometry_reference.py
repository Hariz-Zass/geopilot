from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class GeometryReference(BaseModel):
    """Typed identity for geometry that must be resolved by the server.

    The reference intentionally contains identity/provenance fields but not the
    geometry itself. Clients may transport this object, but the server remains
    authoritative and re-validates every field before returning geometry.
    """

    reference_version: Literal["geometry-reference-v1"] = "geometry-reference-v1"
    project_id: uuid.UUID
    source_type: Literal["site", "gis_feature"]
    source_id: uuid.UUID
    layer_id: uuid.UUID | None = None
    geometry_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    geometry_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_source_shape(self) -> "GeometryReference":
        if self.source_type == "site":
            if self.layer_id is not None:
                raise ValueError("site geometry reference cannot include layer_id")
            if self.geometry_revision is None:
                raise ValueError("site geometry reference requires geometry_revision")
        else:
            if self.layer_id is None:
                raise ValueError("GIS feature geometry reference requires layer_id")
            if self.geometry_revision is not None:
                raise ValueError("GIS feature geometry reference does not use geometry_revision")
        return self


class GeometryResolveRequest(BaseModel):
    reference: GeometryReference


class GeometryResolution(BaseModel):
    reference: GeometryReference
    geometry: dict[str, Any]
    geometry_authority: Literal["server_resolved"] = "server_resolved"
    crs: Literal["EPSG:4326"] = "EPSG:4326"

    @model_validator(mode="after")
    def validate_geometry(self) -> "GeometryResolution":
        if self.geometry.get("type") not in {
            "Point",
            "MultiPoint",
            "LineString",
            "MultiLineString",
            "Polygon",
            "MultiPolygon",
        }:
            raise ValueError("resolved geometry has unsupported GeoJSON type")
        return self
