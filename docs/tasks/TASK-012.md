# TASK-012 — GIS Layer Model

## Status
PASS

## Scope
Introduce project-owned GIS layer metadata and provenance without individual GIS feature persistence.

## Implemented
- `GISLayer` project-owned entity.
- Controlled source kinds: upload, acquired, generated, external_reference.
- CRS identity, source name/URI, optional SHA-256 checksum, geometry-type metadata and provenance JSON.
- Active/archive lifecycle with archived-not-active invariant.
- Authenticated project-scoped CRUD endpoints.
- Cross-owner and cross-project layer substitution rejection.
- Archived projects reject new GIS evidence creation.
- Alembic migration `0005`.

## Explicitly deferred
- GISFeature persistence/geometry ingestion (TASK-013).
- Deterministic spatial calculations (TASK-014).
- GeometryReference/MapAction evidence linkage (TASK-015/016).

## Acceptance
- Backend regression suite: 77/77 PASS.
- Alembic single head: `0005`.
- Offline upgrade and downgrade contract verified.
- `gis_features` table is absent.
- No Git commit created.
