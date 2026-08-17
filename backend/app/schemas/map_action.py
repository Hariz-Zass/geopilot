from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.geometry_reference import GeometryReference, GeometryResolution


class MapAction(BaseModel):
    """Typed map instruction backed only by server-resolvable geometry references."""

    action_version: Literal["map-action-v1"] = "map-action-v1"
    action: Literal["focus", "fit", "highlight"]
    geometry_references: list[GeometryReference] = Field(min_length=1, max_length=100)
    label: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_action_shape(self) -> "MapAction":
        if self.action == "focus" and len(self.geometry_references) != 1:
            raise ValueError("focus map action requires exactly one geometry reference")

        # Duplicate references add no map meaning and can hide malformed evidence envelopes.
        identities = [reference.model_dump_json() for reference in self.geometry_references]
        if len(set(identities)) != len(identities):
            raise ValueError("map action cannot contain duplicate geometry references")
        return self


class MapActionResolveRequest(BaseModel):
    map_action: MapAction


class ResolvedMapAction(BaseModel):
    map_action: MapAction
    resolved_geometries: list[GeometryResolution]
    geometry_authority: Literal["server_resolved"] = "server_resolved"

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> "ResolvedMapAction":
        if len(self.resolved_geometries) != len(self.map_action.geometry_references):
            raise ValueError("every map action geometry reference must resolve exactly once")
        for reference, resolution in zip(
            self.map_action.geometry_references,
            self.resolved_geometries,
            strict=True,
        ):
            if resolution.reference != reference:
                raise ValueError("resolved map action geometry order/identity mismatch")
        return self
