# TASK-015 — GeometryReference

## Status
PASS

## Objective
Introduce a typed server-resolvable geometry identity so clients, findings, and future evidence can reference authoritative Site/GISFeature geometry without embedding client-owned geometry as truth.

## Contract
- `GeometryReference` contains source identity and exact geometry identity, never authoritative geometry payload.
- Supported v1 sources: `site`, `gis_feature`.
- Site references require `geometry_hash` + `geometry_revision`.
- GISFeature references require exact `layer_id` + `geometry_hash`.
- Resolver re-checks authenticated project ownership and exact project/source linkage.
- Archived/unavailable sources fail closed.
- Stale hash/revision references return conflict and are never silently rebound to newer geometry.
- Resolution returns server-derived GeoJSON with `geometry_authority=server_resolved` and EPSG:4326.
- No database migration is required.

## API
`POST /api/v1/projects/{project_id}/geometry/resolve`

## Prohibited scope
MapAction persistence, findings, ToolEvidence, arbitrary client geometry resolution, and derived-buffer persistence are not part of TASK-015.
