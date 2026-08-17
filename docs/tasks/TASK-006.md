# TASK-006 — Database / Alembic Foundation

## Objective
Establish GeoPilot AI's clean migration framework from revision `0001` without introducing Project, Site, authentication, planning, GIS evidence, or other domain tables.

## Implemented
- Alembic configuration and environment wired to runtime `DATABASE_URL`.
- SQLAlchemy declarative `Base` with deterministic constraint naming conventions.
- Process-owned SQLAlchemy engine factory with `pool_pre_ping`.
- Root migration `0001_database_foundation`.
- Idempotent PostGIS and pgvector extension bootstrap.
- Safe downgrade policy: shared extensions are never dropped by schema rollback.
- Offline migration verification script.
- Unit regression coverage for revision identity, empty domain metadata, extension operations and downgrade safety.

## Hard boundaries
- No Project or Site table.
- No authentication schema.
- No planning/evidence/raster/GIS domain schema.
- No old migration history is imported.
- Migration history restarts at `0001` as required by the clean-room rebuild decision.
- No Git commit.

## Acceptance
PASS when unit tests and offline Alembic inspection succeed. Live upgrade against Docker PostgreSQL remains a local-runtime gate because this ChatGPT runtime has no Docker daemon.
