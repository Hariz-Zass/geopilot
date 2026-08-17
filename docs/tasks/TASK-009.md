# TASK-009 — Site Domain

## Scope
Introduce the project-owned target Site as the canonical spatial analysis target.

## Architecture decisions
- Production geometry authority is PostGIS `geometry(MULTIPOLYGON,4326)`.
- API accepts GeoJSON Polygon or MultiPolygon and canonicalizes to MultiPolygon.
- Server validates finite EPSG:4326 coordinates, closed/non-zero rings and obvious self-intersection before persistence; PostGIS `ST_IsValid` remains the database validity gate.
- `geometry_hash` identifies the exact canonical geometry payload.
- `geometry_revision` starts at 1 and increments only when geometry content changes.
- At most one non-archived active Site may exist per Project.
- Site access is nested under an owner-authorized Project boundary.

## Prohibited scope
No GISLayer/GISFeature, spatial analysis tools, map UI, raster domain, planning AI, or document intelligence.

## Acceptance
PASS.

- Full backend suite: 54/54 PASS.
- Alembic single head: `0004`.
- Offline migration contains native `geometry(MULTIPOLYGON,4326)`, GiST index, `ST_IsValid`/non-empty constraint, one-active-site partial unique index, and project cascade FK.
- Polygon input is canonicalized to MultiPolygon.
- Cross-owner access fails at the Project boundary; cross-project Site IDs are not reusable.
- Geometry hash/revision regression coverage confirms revisions increment only when geometry content changes.
- Archived active Sites auto-deactivate; archived Sites cannot reactivate without explicit restore.
- No GISLayer/GISFeature or analysis domain introduced.
- No Git commit created.

Live PostGIS migration/execution remains a local Docker runtime gate.
