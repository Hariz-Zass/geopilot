# TASK-025 — ComplianceFact Domain

## Status
PASS

## Objective
Introduce persisted, project/site-scoped evidence values that can later be consumed by the deterministic Compliance engine without confusing evidence with a compliance conclusion.

## Implemented scope
- Added `ComplianceFact` persistence and migration `0013`.
- Added typed value payloads for numeric, text, boolean, and set facts.
- Added explicit source separation:
  - `user_supplied` via `owner_assertion_v1`
  - `gis_analysis` via `postgis-geography-v1`
- User-supplied facts are explicitly labelled as owner assertions and are not represented as independently measured evidence.
- GIS-derived facts are created only by server-owned deterministic GIS services. The client selects an approved analysis/output but cannot submit the measured GIS value.
- Supported deterministic persistence paths in TASK-025:
  - Site area (`area_sqm` or `area_hectares`)
  - Site-to-GISFeature distance (`distance_m`)
- Persisted exact Site geometry hash/revision for every fact.
- Feature-derived facts persist exact GISLayer/GISFeature IDs and feature geometry hash.
- Added deterministic `provenance_hash` and duplicate-provenance rejection.
- Fact content/source is immutable after creation; API mutation is limited to archive state.
- Facts become unusable if Site geometry identity changes or referenced GIS evidence becomes archived/unavailable/stale.
- GIS evidence referenced by a ComplianceFact uses `ON DELETE RESTRICT` so historical exact lineage cannot be hard-deleted silently.
- Resolution returns explicit limitations and never implies statutory compliance, legal compliance, approval, or a ComplianceFinding.

## API
- `POST /api/v1/projects/{project_id}/sites/{site_id}/compliance-facts/user-supplied`
- `POST /api/v1/projects/{project_id}/sites/{site_id}/compliance-facts/from-gis`
- `GET /api/v1/projects/{project_id}/sites/{site_id}/compliance-facts`
- `GET /api/v1/projects/{project_id}/sites/{site_id}/compliance-facts/{fact_id}`
- `PATCH /api/v1/projects/{project_id}/sites/{site_id}/compliance-facts/{fact_id}`
- `POST /api/v1/projects/{project_id}/sites/{site_id}/compliance-facts/{fact_id}/resolve`

## Hard boundaries
- TASK-025 does **not** execute PolicyCriterion operators.
- TASK-025 does **not** create ComplianceRun or ComplianceFinding records.
- A validated ComplianceFact is evidence only.
- Client-supplied GIS measurements are rejected by schema contract.
- Archived/inactive analytical context fails closed for creation/use.

## Acceptance
- Focused TASK-025 tests: 14/14 PASS.
- Full backend regression: 220/220 PASS, executed as 111 + 109 split to stay within environment command timeout.
- Python compile gate: PASS.
- Alembic single head: `0013`.
- Offline PostgreSQL upgrade `0012 -> 0013`: PASS.
- Offline PostgreSQL downgrade `0013 -> 0012`: PASS.
- No Git commit created.

## Next
TASK-026 — Deterministic Compliance Engine.
