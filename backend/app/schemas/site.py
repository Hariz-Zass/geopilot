from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Position: TypeAlias = tuple[float, float]
LinearRing: TypeAlias = list[Position]
PolygonCoordinates: TypeAlias = list[LinearRing]
MultiPolygonCoordinates: TypeAlias = list[PolygonCoordinates]


class PolygonGeometry(BaseModel):
    type: Literal["Polygon"]
    coordinates: PolygonCoordinates


class MultiPolygonGeometry(BaseModel):
    type: Literal["MultiPolygon"]
    coordinates: MultiPolygonCoordinates


GeoJSONGeometry = Annotated[PolygonGeometry | MultiPolygonGeometry, Field(discriminator="type")]


def _orientation(a: Position, b: Position, c: Position) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Position, b: Position, c: Position) -> bool:
    return (
        min(a[0], c[0]) <= b[0] <= max(a[0], c[0])
        and min(a[1], c[1]) <= b[1] <= max(a[1], c[1])
    )


def _segments_intersect(a: Position, b: Position, c: Position, d: Position) -> bool:
    eps = 1e-12
    o1, o2, o3, o4 = _orientation(a, b, c), _orientation(a, b, d), _orientation(c, d, a), _orientation(c, d, b)
    if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and (
        (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)
    ):
        return True
    if abs(o1) <= eps and _on_segment(a, c, b):
        return True
    if abs(o2) <= eps and _on_segment(a, d, b):
        return True
    if abs(o3) <= eps and _on_segment(c, a, d):
        return True
    if abs(o4) <= eps and _on_segment(c, b, d):
        return True
    return False


def _validate_ring(ring: LinearRing) -> None:
    if len(ring) < 4:
        raise ValueError("each linear ring must contain at least four positions")
    if ring[0] != ring[-1]:
        raise ValueError("each linear ring must be closed")
    for lon, lat in ring:
        if not (math.isfinite(lon) and math.isfinite(lat)):
            raise ValueError("coordinates must be finite numbers")
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("coordinates must be valid EPSG:4326 longitude/latitude values")

    twice_area = sum(
        ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
        for i in range(len(ring) - 1)
    )
    if abs(twice_area) <= 1e-14:
        raise ValueError("linear rings must enclose a non-zero area")

    segments = [(ring[i], ring[i + 1]) for i in range(len(ring) - 1)]
    for i, (a, b) in enumerate(segments):
        for j, (c, d) in enumerate(segments):
            if j <= i + 1:
                continue
            if i == 0 and j == len(segments) - 1:
                continue
            if _segments_intersect(a, b, c, d):
                raise ValueError("linear rings must not self-intersect")


def _validate_coordinates(coords: MultiPolygonCoordinates) -> MultiPolygonCoordinates:
    if not coords:
        raise ValueError("geometry must contain at least one polygon")
    for polygon in coords:
        if not polygon:
            raise ValueError("each polygon must contain an exterior ring")
        for ring in polygon:
            _validate_ring(ring)
    return coords


def canonical_multipolygon(geometry: PolygonGeometry | MultiPolygonGeometry) -> MultiPolygonCoordinates:
    coords = [geometry.coordinates] if geometry.type == "Polygon" else geometry.coordinates
    return _validate_coordinates(coords)


def _fmt(value: float) -> str:
    rendered = f"{value:.12f}".rstrip("0").rstrip(".")
    return "0" if rendered in {"-0", ""} else rendered


def multipolygon_to_ewkt(coords: MultiPolygonCoordinates) -> str:
    polygons: list[str] = []
    for polygon in coords:
        rings = []
        for ring in polygon:
            rings.append("(" + ",".join(f"{_fmt(x)} {_fmt(y)}" for x, y in ring) + ")")
        polygons.append("(" + ",".join(rings) + ")")
    return "SRID=4326;MULTIPOLYGON(" + ",".join(polygons) + ")"


def canonical_geojson(coords: MultiPolygonCoordinates) -> dict[str, object]:
    return {"type": "MultiPolygon", "coordinates": coords}


def geometry_digest(coords: MultiPolygonCoordinates) -> str:
    payload = json.dumps(canonical_geojson(coords), separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ewkt_to_geojson(ewkt: str) -> dict[str, object]:
    # Site EWKT is server-generated from validated 2D MULTIPOLYGON coordinates.
    prefix = "SRID=4326;MULTIPOLYGON("
    if not ewkt.startswith(prefix) or not ewkt.endswith(")"):
        raise ValueError("unexpected persisted site geometry representation")
    body = ewkt[len("SRID=4326;"):]
    # Minimal recursive parser for the server-owned MULTIPOLYGON EWKT subset.
    text = body[len("MULTIPOLYGON") :]
    index = 0

    def skip_ws() -> None:
        nonlocal index
        while index < len(text) and text[index].isspace():
            index += 1

    def expect(char: str) -> None:
        nonlocal index
        skip_ws()
        if index >= len(text) or text[index] != char:
            raise ValueError("malformed persisted site geometry")
        index += 1

    def number() -> float:
        nonlocal index
        skip_ws()
        start = index
        while index < len(text) and text[index] not in " ,()":
            index += 1
        try:
            return float(text[start:index])
        except ValueError as exc:
            raise ValueError("malformed persisted coordinate") from exc

    polygons: MultiPolygonCoordinates = []
    expect("(")
    while True:
        expect("(")
        polygon: PolygonCoordinates = []
        while True:
            expect("(")
            ring: LinearRing = []
            while True:
                x = number()
                y = number()
                ring.append((x, y))
                skip_ws()
                if index < len(text) and text[index] == ",":
                    index += 1
                    continue
                break
            expect(")")
            polygon.append(ring)
            skip_ws()
            if index < len(text) and text[index] == ",":
                index += 1
                continue
            break
        expect(")")
        polygons.append(polygon)
        skip_ws()
        if index < len(text) and text[index] == ",":
            index += 1
            continue
        break
    expect(")")
    skip_ws()
    if index != len(text):
        raise ValueError("malformed persisted site geometry")
    return canonical_geojson(polygons)


class SiteCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    geometry: GeoJSONGeometry
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned

    @model_validator(mode="after")
    def validate_geometry(self) -> "SiteCreateRequest":
        canonical_multipolygon(self.geometry)
        return self


class SiteUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    geometry: GeoJSONGeometry | None = None
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

    @model_validator(mode="after")
    def validate_state_and_geometry(self) -> "SiteUpdateRequest":
        if self.geometry is not None:
            canonical_multipolygon(self.geometry)
        if self.is_archived is True and self.is_active is True:
            raise ValueError("an archived site cannot be active")
        return self


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    geometry: dict[str, object]
    geometry_hash: str
    geometry_revision: int
    is_active: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
