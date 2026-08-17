# TASK-004 — FastAPI Backend Foundation

## Objective
Create a stable application-layer foundation before domain implementation.

## Scope
- application factory and lifecycle
- API versioning
- typed runtime configuration
- request correlation IDs
- structured logging foundation
- CORS
- stable error contract
- OpenAPI/docs
- backend test harness

## Explicitly out of scope
Authentication, Project/Site models, migrations, GIS logic, document ingestion, AI providers and Planning Officer behavior.

## Acceptance
1. `GET /api/v1/system/health` returns process liveness.
2. `GET /api/v1/system/ready` preserves TASK-003 database readiness behavior.
3. Every normal HTTP response carries `X-Request-ID`.
4. Invalid caller request IDs are replaced by server-generated UUIDs.
5. HTTP/application/validation failures use the common error envelope.
6. CORS is explicit and environment-configurable.
7. OpenAPI exposes versioned endpoints.
8. Unit tests pass without requiring a live database.
9. No domain persistence or migrations are introduced.
10. No Git commit is created.
