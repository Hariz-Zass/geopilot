# TASK-021 — Hybrid Retrieval

## Scope
Project-scoped deterministic document retrieval combining PostgreSQL full-text keyword search and pgvector cosine similarity, fused using Reciprocal Rank Fusion (RRF). Exact document/version/page/chunk provenance is returned with every hit.

## Hard boundaries
- Retrieval is project-scoped and excludes archived PlanningDocuments.
- Keyword and vector scores are never treated as policy applicability or statutory truth.
- Vector comparison is valid only against the exact persisted embedding provider/model/dimension lineage.
- Provider failure degrades visibly to keyword-only retrieval; it is never hidden.
- No HNSW/IVFFlat index is introduced in this task; vector search remains exact.
- No citation rendering/synthesis promotion is introduced; TASK-022 owns the citation/provenance presentation contract.

## Ranking
Production keyword retrieval uses PostgreSQL `websearch_to_tsquery` + `ts_rank_cd` with `simple` configuration. Vector retrieval uses pgvector cosine distance `<=>`. Results are fused by weighted Reciprocal Rank Fusion with `k=60`, then deterministically tie-broken by chunk UUID.

## Endpoint
`POST /api/v1/projects/{project_id}/document-search`

## Acceptance
See backend regression tests and PROJECT_STATE.md.
