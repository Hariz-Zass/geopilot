from __future__ import annotations

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import func
from sqlalchemy.types import UserDefinedType


class _EWKTGeometry(UserDefinedType[str]):
    cache_ok = True
    geometry_spec = "geometry(Geometry,4326)"

    def get_col_spec(self, **kw: object) -> str:
        return self.geometry_spec

    def bind_expression(self, bindvalue):  # type: ignore[no-untyped-def]
        return func.ST_GeomFromEWKT(bindvalue, type_=self)

    def column_expression(self, col):  # type: ignore[no-untyped-def]
        return func.ST_AsEWKT(col)


class MultiPolygon4326(_EWKTGeometry):
    """PostGIS MULTIPOLYGON(4326), represented as EWKT at the ORM boundary."""

    geometry_spec = "geometry(MULTIPOLYGON,4326)"


class Geometry4326(_EWKTGeometry):
    """Generic 2D PostGIS geometry constrained to SRID 4326.

    GISFeature can hold Point/MultiPoint/LineString/MultiLineString/Polygon/
    MultiPolygon while retaining one native spatial column and a GiST index.
    """

    geometry_spec = "geometry(Geometry,4326)"


@compiles(MultiPolygon4326, "sqlite")
def _compile_multipolygon_sqlite(type_: MultiPolygon4326, compiler, **kw: object) -> str:  # type: ignore[no-untyped-def]
    return "TEXT"


@compiles(MultiPolygon4326, "postgresql")
def _compile_multipolygon_postgresql(type_: MultiPolygon4326, compiler, **kw: object) -> str:  # type: ignore[no-untyped-def]
    return type_.geometry_spec


@compiles(Geometry4326, "sqlite")
def _compile_geometry_sqlite(type_: Geometry4326, compiler, **kw: object) -> str:  # type: ignore[no-untyped-def]
    return "TEXT"


@compiles(Geometry4326, "postgresql")
def _compile_geometry_postgresql(type_: Geometry4326, compiler, **kw: object) -> str:  # type: ignore[no-untyped-def]
    return type_.geometry_spec
