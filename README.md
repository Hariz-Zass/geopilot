# GeoPilot AI

GeoPilot AI is an evidence-first, AI-powered town-planning decision-support system.

## Rebuild status

Clean-room rebuild started from TASK-001. No legacy source code, database, migrations, or evidence are imported.

## Authoritative architecture

The rebuild follows the GeoPilot AI Master System Developer Handover v1.0 (14 August 2026) and the matching repository architecture handover.

Core flow:

User Browser -> Frontend Planning Workspace -> Authenticated API -> Planning Officer / PlanningRun Orchestrator -> Server-owned Tool Registry -> Domain Services -> PostgreSQL/PostGIS/pgvector evidence -> ToolEvidence / Findings / GeometryReference / MapAction -> Grounded Synthesis -> Frontend review experience.

## Product boundary

GeoPilot AI is a planning decision-support system. It is not a statutory approval, legal decision, or autonomous planning-permission engine.

## Planned local stack

- Frontend: React + TypeScript + Vite
- Map: MapLibre GL JS
- Backend: Python + FastAPI + Pydantic + SQLAlchemy
- Database: PostgreSQL + PostGIS + pgvector
- Migrations: Alembic, new clean sequence beginning at 0001
- GIS: PostGIS first; GeoPandas/Shapely/PyProj where service-side processing is justified
- Raster: Rasterio/GDAL-based deterministic services
- Satellite: Sentinel-2 primary provider, provider adapter architecture
- AI providers: Ollama local provider + OpenAI GPT-5.6 Luna provider
- Runtime: Docker Compose

## Git policy during rebuild

A repository may be initialized for worktree tracking, but no commits, tags, or pushes are authorized until the owner explicitly approves after project completion.

## Local runtime bootstrap

1. Install Docker Desktop with Docker Compose support.
2. Copy `.env.example` to `.env` and replace the local database password.
3. Run `docker compose up --build -d` (or `./scripts/bootstrap-local.sh` on a shell that supports it).
4. Backend health: `http://localhost:8000/health`.
5. Frontend: `http://localhost:5173`.
6. Run `./scripts/verify-runtime.sh` to verify the backend, frontend and required database extensions.

TASK-002 intentionally contains only runtime scaffolding. Domain schemas and the clean Alembic migration sequence are introduced later.

TASK-004 backend application foundation added.


## Current rebuild checkpoint
TASK-011 implements the first server-authoritative MapLibre planning map. See `PROJECT_STATE.md` and `docs/tasks/TASK-011.md`.


## Current rebuild checkpoint
TASK-014 PASS — deterministic PostGIS GIS analysis is implemented for site area, feature distance/nearest ranking, overlap/intersection and server-derived buffers. Next: TASK-015 GeometryReference.


## Current rebuild checkpoint
TASK-016 PASS — MapAction Service. Next: TASK-017 PlanningDocument Model.

### Rebuild checkpoint: TASK-019
Planning-document text can now be transformed into deterministic, page-local chunks with exact page IDs, page numbers, character offsets, SHA-256 hashes and stable UUIDv5 identities. No embeddings are created by TASK-019; vector indexing begins in TASK-020.

### Rebuild checkpoint: TASK-020
Document chunks can now be embedded through a server-owned hybrid embedding provider layer (Ollama primary, OpenAI fallback/configurable) and persisted with exact provider/model/dimension provenance in PostgreSQL pgvector. TASK-021 adds project-scoped keyword + vector hybrid retrieval; TASK-020 does not yet rank/search evidence.

### TASK-022 Citation / Provenance Engine
Document search hits carry immutable citation references. Resolve them through `POST /api/v1/projects/{project_id}/citations/resolve` before downstream evidence use. Resolution is server-owned and validates exact document/version/page/chunk identities, recorded and recomputed hashes, page range provenance, ownership/state, and source availability. A valid citation proves provenance of the quoted passage; it does not by itself prove planning-policy applicability.

## Rebuild checkpoint — TASK-023
PolicyReference workflow is implemented. Validated document citations can now become reviewed project-scoped policy representations while preserving exact source wording, source hashes, page/chunk lineage, reviewer state and applicability limitations. Only explicitly verified final references can be resolved for downstream deterministic policy use; PolicyCriterion construction remains TASK-024.

## Rebuild checkpoint — TASK-024
PolicyCriterion Domain is implemented. Only verified PolicyReference evidence can become deterministic rule candidates, and numeric thresholds/range bounds must be explicitly present in the exact cited source passage. Criteria require explicit review before deterministic use; this task does not yet create ComplianceFact records or execute Compliance.

## Rebuild checkpoint — TASK-025
ComplianceFact Domain is implemented. GeoPilot can now persist site-scoped evidence as explicit owner assertions or server-derived deterministic GIS measurements while preserving exact Site/GIS provenance. ComplianceFact resolution revalidates source identity and clearly states that a fact is evidence only; PolicyCriterion comparison and ComplianceFinding creation begin in TASK-026.

## PLAN-Ai 2026 Track B — AI Planner Decision Workspace

Track B now includes a closed-evidence AI decision workflow that converts deterministic satellite temporal measurements into a planner-facing brief: **Issue → Evidence → non-statutory triage priority → Planning implication → Recommended action → Verification need → Limitations**. A planner can supply a question/problem statement, while numeric claims and evidence references remain server-validated against organizer-supplied evidence.

