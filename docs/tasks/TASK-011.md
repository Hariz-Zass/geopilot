# TASK-011 — MapLibre Planning Map

## Status
IMPLEMENTATION COMPLETE / FRONTEND DEPENDENCY-BACKED ACCEPTANCE PENDING

## Objective
Introduce the first spatial frontend experience without allowing the browser to become an authority for Site identity or geometry.

## Scope delivered
- MapLibre GL JS dependency and CSS integration.
- `/projects/:projectId/map` route.
- Dedicated authenticated `GET /api/v1/projects/{project_id}/sites/active` backend endpoint.
- Active-Site API contract carrying exact server geometry, geometry hash and geometry revision.
- Map source/layers built only from the server-returned active Site.
- Camera bounds derived client-side strictly for presentation/fit-to-site behavior.
- Map loading, unauthenticated, no-active-Site, API error and degraded-renderer states.
- Session-token read boundary using browser sessionStorage; no token is embedded in Vite environment variables or source.
- Geometry/provenance unit tests authored for the frontend.

## Authority contract
1. The browser never decides which Site is active; the backend returns the server-designated active Site.
2. The map does not rewrite, buffer, simplify or otherwise mutate authoritative Site geometry.
3. Viewport bounds are a presentation-only derivative and are not persisted as evidence.
4. Geometry identity remains the exact backend `geometry_hash` + `geometry_revision`.
5. A Site that is inactive or archived is refused by the frontend active-context feature builder even if malformed client state attempts to provide it.
6. Map/basemap failure degrades the visual experience; it does not invalidate or replace server evidence.
7. Cross-owner Project access remains hidden through the existing isolation boundary.

## Persistence
No migration. Alembic head remains `0004`.

## Acceptance evidence
- Full backend regression suite: 66 passed.
- Active-Site endpoint tests cover normal active geometry, no-active-Site, and foreign-project hiding.
- Frontend geometry/API/session tests are present.
- Frontend `typecheck/test/lint/build` cannot yet execute in this runtime because npm registry DNS/network access remains unavailable (`EAI_AGAIN`).
- No Git commit created.

## Deferred runtime gates
- `npm install` / lockfile creation and dependency-backed frontend verification on a network-enabled runtime.
- Browser WebGL/manual map acceptance.
- Live backend/PostGIS migration/runtime acceptance through Docker on the owner's machine.

## Explicit non-scope
- GISLayer/GISFeature ingestion.
- Drawing/editing Site geometry on the map.
- Authoritative measurements in the browser.
- Planning findings/MapAction contracts.
- Raster/satellite layers.
