from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceKind = Literal["upload", "acquired", "generated", "external_reference"]
GeometryType = Literal["Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "Mixed", "Unknown"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CRS = re.compile(r"^(EPSG:\d{3,6}|[A-Za-z0-9_.:-]{2,64})$")


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class GISLayerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    source_kind: SourceKind
    source_name: str | None = Field(default=None, max_length=255)
    source_uri: str | None = Field(default=None, max_length=4096)
    source_checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    source_crs: str = Field(min_length=2, max_length=64)
    geometry_type: GeometryType | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned

    @field_validator("description", "source_name", "source_uri")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        return _clean_text(value)

    @field_validator("source_checksum_sha256")
    @classmethod
    def checksum(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.lower()
        if not _SHA256.fullmatch(value):
            raise ValueError("source_checksum_sha256 must be 64 lowercase hexadecimal characters")
        return value

    @field_validator("source_crs")
    @classmethod
    def crs(cls, value: str) -> str:
        value = value.strip()
        if value.lower().startswith("epsg:"):
            value = "EPSG:" + value.split(":", 1)[1]
        if not _CRS.fullmatch(value):
            raise ValueError("source_crs must be a controlled CRS identifier such as EPSG:4326")
        return value

    @model_validator(mode="after")
    def source_identity(self):
        if self.source_kind == "upload" and not self.source_name:
            raise ValueError("upload layers require source_name")
        if self.source_kind in {"acquired", "external_reference"} and not self.source_uri:
            raise ValueError(f"{self.source_kind} layers require source_uri")
        return self


class GISLayerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    geometry_type: GeometryType | None = None
    provenance: dict[str, Any] | None = None
    is_active: bool | None = None
    is_archived: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _clean_text(value)

    @model_validator(mode="after")
    def archive_state(self):
        if self.is_archived is True and self.is_active is True:
            raise ValueError("an archived GIS layer cannot be active")
        return self


class GISLayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    source_kind: str
    source_name: str | None
    source_uri: str | None
    source_checksum_sha256: str | None
    source_crs: str
    geometry_type: str | None
    provenance: dict[str, Any]
    is_active: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
