# TASK-014 — Deterministic GIS Analysis

## Objective
Create the first authoritative GIS calculation service. Spatial measurements are produced by PostGIS, never by the LLM or frontend.

## Implemented
- Site area in square metres and hectares.
- Exact feature-to-site distance in metres.
- Nearest project-owned GIS features with optional distance bound.
- Site/feature intersection and overlap measurements.
- Server-derived site buffer geometry and area.
- Active Project/Site/GISLayer and non-archived GISFeature gates.
- Typed deterministic result contracts carrying exact site/feature geometry identities.
- API routes under `/projects/{project_id}/sites/{site_id}/analysis/gis`.

## Authority and units
WGS84 stored geometry is cast to PostGIS `geography` for metric measurements. Site area and polygon intersection area are returned in square metres; distance and buffer radius are metres. Hectares and percentages are deterministic derivations of server measurements.

## Buffer boundary
TASK-014 buffer geometry is explicitly `ephemeral_server_derived`. It is not a persisted evidence identity and must not be treated as a `GeometryReference`; durable geometry identity belongs to TASK-015.

## Explicitly out of scope
- GeometryReference persistence/contracts (TASK-015).
- MapAction (TASK-016).
- Document/policy intelligence.
- AI-generated spatial measurements.
- New database migration.

## Acceptance
- All backend regression tests pass.
- Alembic remains at a single `0006` head.
- No migration introduced.
- Production SQL uses PostGIS geography measurement functions.
- Scope/evidence state failures fail closed.
- Repository remains uncommitted.
