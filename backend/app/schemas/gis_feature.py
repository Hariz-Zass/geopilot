from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

GeometryType = Literal["Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"]
Position = list[float]


def _validate_position(position: Any) -> Position:
    if not isinstance(position, (list, tuple)) or len(position) < 2:
        raise ValueError("each position must contain longitude and latitude")
    x, y = position[0], position[1]
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise ValueError("coordinates must be numeric")
    x, y = float(x), float(y)
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("coordinates must be finite")
    if not (-180 <= x <= 180 and -90 <= y <= 90):
        raise ValueError("coordinates must be valid EPSG:4326 longitude/latitude values")
    return [x, y]


def _positions(value: Any, depth: int) -> Any:
    if depth == 0:
        return _validate_position(value)
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("geometry coordinates must not be empty")
    return [_positions(item, depth - 1) for item in value]


def _ring_area(ring: list[Position]) -> float:
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2


def validate_geometry_payload(geometry_type: str, coordinates: Any) -> Any:
    depths = {
        "Point": 0,
        "MultiPoint": 1,
        "LineString": 1,
        "MultiLineString": 2,
        "Polygon": 2,
        "MultiPolygon": 3,
    }
    if geometry_type not in depths:
        raise ValueError("unsupported GeoJSON geometry type")
    normalized = _positions(coordinates, depths[geometry_type])

    lines: list[list[Position]] = []
    rings: list[list[Position]] = []
    if geometry_type == "LineString": lines = [normalized]
    elif geometry_type == "MultiLineString": lines = normalized
    elif geometry_type == "Polygon": rings = normalized
    elif geometry_type == "MultiPolygon": rings = [ring for polygon in normalized for ring in polygon]
    for line in lines:
        if len(line) < 2:
            raise ValueError("LineString parts must contain at least two positions")
    for ring in rings:
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("polygon rings must contain at least four positions and be closed")
        if abs(_ring_area(ring)) <= 1e-14:
            raise ValueError("polygon rings must enclose a non-zero area")
    return normalized


def _fmt(value: float) -> str:
    rendered = f"{value:.12f}".rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _pair(position: Position) -> str:
    return f"{_fmt(position[0])} {_fmt(position[1])}"


def geometry_to_ewkt(geometry: "GeoJSONGeometry") -> str:
    t, c = geometry.type, geometry.coordinates
    if t == "Point": body = _pair(c)
    elif t == "MultiPoint": body = ",".join(f"({_pair(p)})" for p in c)
    elif t == "LineString": body = ",".join(_pair(p) for p in c)
    elif t == "MultiLineString": body = ",".join("(" + ",".join(_pair(p) for p in line) + ")" for line in c)
    elif t == "Polygon": body = ",".join("(" + ",".join(_pair(p) for p in ring) + ")" for ring in c)
    else:
        body = ",".join("(" + ",".join("(" + ",".join(_pair(p) for p in ring) + ")" for ring in polygon) + ")" for polygon in c)
    return f"SRID=4326;{t.upper()}({body})"


def geometry_digest(geometry: "GeoJSONGeometry") -> str:
    payload = json.dumps({"type": geometry.type, "coordinates": geometry.coordinates}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def ewkt_to_geometry(ewkt: str) -> dict[str, Any]:
    if not ewkt.startswith("SRID=4326;"):
        raise ValueError("unexpected persisted GIS feature SRID")
    wkt = ewkt[len("SRID=4326;"):]
    name, _, text = wkt.partition("(")
    tmap = {"POINT":"Point","MULTIPOINT":"MultiPoint","LINESTRING":"LineString","MULTILINESTRING":"MultiLineString","POLYGON":"Polygon","MULTIPOLYGON":"MultiPolygon"}
    if name not in tmap or not text.endswith(")"):
        raise ValueError("unexpected persisted GIS feature geometry")
    text = "(" + text
    i = 0

    def ws():
        nonlocal i
        while i < len(text) and text[i].isspace(): i += 1
    def expect(ch: str):
        nonlocal i
        ws()
        if i >= len(text) or text[i] != ch: raise ValueError("malformed persisted GIS feature geometry")
        i += 1
    def num() -> float:
        nonlocal i
        ws(); start=i
        while i < len(text) and text[i] not in " ,()": i += 1
        return float(text[start:i])
    def pos() -> Position:
        return [num(), num()]
    # Generic recursive WKT parenthesis parser; leaves coordinate pairs as tuples.
    i = 0
    def parse_group():
        nonlocal i
        expect("("); items=[]
        while True:
            ws()
            if i < len(text) and text[i] == "(": item=parse_group()
            else: item=pos()
            items.append(item); ws()
            if i < len(text) and text[i] == ",": i += 1; continue
            break
        expect(")"); return items
    parsed=parse_group(); ws()
    if i != len(text): raise ValueError("malformed persisted GIS feature geometry")
    gtype=tmap[name]
    if gtype == "Point": coords=parsed[0]
    elif gtype == "MultiPoint": coords=[x[0] if isinstance(x, list) and len(x)==1 and isinstance(x[0], list) else x for x in parsed]
    else: coords=parsed
    return {"type":gtype,"coordinates":coords}


class GeoJSONGeometry(BaseModel):
    type: GeometryType
    coordinates: Any

    @model_validator(mode="after")
    def valid(self):
        self.coordinates = validate_geometry_payload(self.type, self.coordinates)
        return self


class GISFeatureInput(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str | int | None = None
    geometry: GeoJSONGeometry
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("properties")
    @classmethod
    def json_properties(cls, value: dict[str, Any]) -> dict[str, Any]:
        try: json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc: raise ValueError("properties must be valid finite JSON") from exc
        return value


class GISFeatureCreateRequest(BaseModel):
    source_feature_id: str | None = Field(default=None, max_length=512)
    geometry: GeoJSONGeometry
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_feature_id")
    @classmethod
    def clean_id(cls, value: str | None) -> str | None:
        if value is None: return None
        value=value.strip()
        return value or None

    @field_validator("properties")
    @classmethod
    def json_properties(cls, value: dict[str, Any]) -> dict[str, Any]:
        try: json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc: raise ValueError("properties must be valid finite JSON") from exc
        return value


class GISFeatureCollectionRequest(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GISFeatureInput] = Field(min_length=1, max_length=5000)


class GISFeatureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    layer_id: uuid.UUID
    source_feature_id: str | None
    geometry: dict[str, Any]
    geometry_type: str
    geometry_hash: str
    properties: dict[str, Any]
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class GISFeatureCollectionResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    count: int
    features: list[GISFeatureResponse]
