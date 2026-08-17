# Architecture Baseline — TASK-001

## Status
LOCKED FOR CLEAN-ROOM REBUILD

## System shape

### Frontend
A typed React/TypeScript planning workspace centered on active Project, active Site, interactive MapLibre map, Planning Officer interaction, PlanningRun progress, findings, evidence/provenance, limitations, professional-review actions, and Advanced Review workflows.

### Backend
A Python/FastAPI domain-service architecture. Business truth lives in typed services and deterministic engines, not in prompts.

### Database
PostgreSQL is the durable system of record. PostGIS owns spatial operations and spatial identity. pgvector supports embedding-backed retrieval. All schema history starts from a new Alembic 0001 migration.

### AI provider architecture
`AIProvider` is an application interface, not a domain service.

Planned providers:
- `OllamaProvider`: local/default-capable provider.
- `OpenAIProvider`: remote provider using GPT-5.6 Luna by owner decision.

Provider selection may vary by environment, health, cost, capability, or explicit user choice, but provider output never becomes authoritative evidence merely because it came from a model.

### Satellite provider architecture
`SatelliteProvider` is an adapter boundary.

v1 primary source: Sentinel-2.
Future sources may be added without rewriting temporal-analysis domain logic.

### Planning-document architecture
Two controlled ingestion paths are required:
1. User upload of RFN, RSN, RT, RKK, GPP, circulars, technical guidelines, and other controlled planning material.
2. Controlled document acquisition/import using an allowlisted provider/source mechanism with provenance capture, review state, and immutable source/version identity.

Acquired text is never automatically promoted to verified policy truth.

## Core domain boundaries

- Identity/Auth
- Project
- Site
- Document Intelligence
- Policy Evidence
- GIS / Spatial Analysis
- Compliance
- Suitability
- Raster / Satellite
- Temporal Intelligence
- PlanningRun / Orchestration
- Tool Registry
- ToolEvidence / Findings
- GeometryReference / MapAction
- Grounded Synthesis
- Professional Review
- Reporting
- Audit

## Canonical request flow

Question
-> active Project/Site validation
-> bounded intent
-> structured PlanningRun
-> approved server-owned tool plan
-> deterministic/retrieval services
-> typed ToolEvidence
-> evidence validation
-> grounded synthesis
-> findings / server-owned map actions
-> limitations / unresolved states
-> professional review.

## Clean-room constraint

No old code, database records, migration revisions, evidence records, or persisted IDs are imported. Historical handover knowledge is used only as specification input.
