# TASK-013 — GIS Feature Ingestion

## Status
PASS

## Scope
Introduce project/layer-owned GIS feature persistence and controlled GeoJSON ingestion without implementing spatial-analysis calculations.

## Implemented
- `GISFeature` entity linked exactly to both `project_id` and `layer_id`.
- Native PostGIS `geometry(Geometry,4326)` authority with GiST index.
- Supported GeoJSON geometry types: Point, MultiPoint, LineString, MultiLineString, Polygon and MultiPolygon.
- Exact `geometry_hash`, generated feature UUID and optional source feature identifier.
- JSON feature properties and archive lifecycle.
- Single-feature creation plus atomic GeoJSON FeatureCollection ingestion (maximum 5,000 features/request).
- EPSG:4326 coordinate, line/ring and JSON validation at API boundary.
- Database hard gates for SRID 4326, non-empty geometry and `ST_IsValid`.
- Layer geometry-type enforcement; Unknown layers adopt the first accepted feature type, while Mixed layers explicitly permit mixed geometry.
- Ingestion allowed only into active, non-archived GIS layers.
- Cross-owner, cross-project and cross-layer feature-ID substitution rejection.
- Alembic migration `0006`.

## Explicitly deferred
- Distance/area/intersection/buffer/nearest calculations (TASK-014).
- GeometryReference contracts (TASK-015).
- MapAction contracts (TASK-016).
- File upload parsing beyond validated GeoJSON request payloads; document/source acquisition remains a later controlled workflow.

## Acceptance
- Backend regression suite: 92/92 PASS.
- Alembic single head: `0006`.
- Offline upgrade verifies native PostGIS geometry, GiST index and spatial validity constraints.
- Offline downgrade `0006 -> 0005` removes only `gis_features`.
- Atomic batch rollback regression verified.
- No Git commit created.
