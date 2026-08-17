# TASK-003 — PostgreSQL + PostGIS + pgvector Database Foundation

Status: PASS (static/unit validation in ChatGPT build environment; live Docker/database smoke test remains host-runtime verification)

## Objective
Establish an explicit database readiness contract for the clean-room GeoPilot runtime before any domain schema or migration exists.

## Capabilities established
- PostgreSQL 16+ is the minimum supported database runtime.
- `postgis` and `vector` are mandatory extensions.
- `/health` remains backend process liveness only.
- `/ready` fails closed with HTTP 503 unless database connectivity and required extensions are available.
- Database capability metadata is returned without exposing credentials.
- Dedicated host verification checks PostgreSQL identity, extension versions, PostGIS capability and a pgvector type smoke test.

## Hard boundaries
- No project/site/document/policy/GIS/compliance/suitability/raster domain tables.
- No Alembic migration yet; clean migration sequence still begins in TASK-006.
- No legacy database records or schema imported.
- No Git commit/tag/push.

## Acceptance
1. Required-extension contract explicitly requires `postgis` and `vector`.
2. PostgreSQL versions below 16 fail readiness.
3. Missing extensions fail readiness.
4. Connection/capability exceptions fail closed without leaking the DSN or password.
5. `/ready` reflects database readiness while `/health` remains liveness-only.
6. Backend Compose healthcheck uses `/ready`.
7. Database verification script checks PostGIS and pgvector behavior.
8. Unit tests cover ready, missing-extension, unsupported-version and empty-result states.
9. No domain migration/schema introduced.
