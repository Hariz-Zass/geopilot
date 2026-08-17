# TASK-002 — Docker Local Environment

Status: PASS (static validation in ChatGPT build environment; host Docker execution required on owner machine)

## Objective
Establish a deterministic local development runtime for GeoPilot AI without introducing planning-domain logic.

## Runtime services
- `db`: PostgreSQL 16 + PostGIS 3.5 + pgvector, persistent volume.
- `backend`: Python 3.12 + FastAPI, `/health` endpoint.
- `frontend`: Node 22 + React/TypeScript/Vite placeholder shell.

## Hard boundaries
- No legacy code/database/evidence imported.
- No domain schema or Alembic migration yet; migration sequence starts in TASK-006.
- No AI, GIS-analysis, document, policy, compliance, suitability, raster or satellite business logic yet.
- No Git commit/tag/push.

## Acceptance
1. Compose file parses.
2. Database image includes PostGIS and pgvector installation path.
3. Init script enables `postgis` and `vector` extensions.
4. PostgreSQL data persists in named volume.
5. Backend waits for healthy database and exposes `/health`.
6. Frontend waits for backend health and serves Vite shell.
7. Local Ollama host path remains reachable through `host.docker.internal`.
8. Secrets remain outside source control via `.env`.
