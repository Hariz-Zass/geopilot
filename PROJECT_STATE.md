# GeoPilot AI — Project State

## Current rebuild state
- TASK-001 — PASS — Repository & Architecture Baseline
- TASK-002 — PASS (static/runtime config acceptance; Docker smoke test pending local Docker daemon)
- TASK-003 — PASS (database readiness unit acceptance; live DB smoke test pending local Docker daemon)
- TASK-004 — PASS — FastAPI Backend Foundation
- TASK-005 — IMPLEMENTATION COMPLETE / dependency-backed frontend acceptance pending because npm registry timed out in the ChatGPT runtime
- TASK-006 — PASS — Database / Alembic Foundation
- TASK-007 — PASS — User / Authentication Foundation
- TASK-008 — PASS — Project Domain
- TASK-009 — PASS — Site Domain
- TASK-010 — PASS — Project/Site Isolation Gate
- TASK-011 — IMPLEMENTATION COMPLETE — MapLibre Planning Map (frontend dependency-backed/browser acceptance pending)

## TASK-009 acceptance evidence
- `Site` is project-owned and all access is authorized through the authenticated Project boundary.
- Production geometry authority is native PostGIS `geometry(MULTIPOLYGON,4326)`.
- GeoJSON Polygon/MultiPolygon input is canonicalized to MultiPolygon.
- Input validation covers finite EPSG:4326 coordinates, closed/non-zero rings and self-intersection; PostGIS `ST_IsValid` + `ST_IsEmpty` is the database hard gate.
- Exact spatial identity is represented by `geometry_hash` plus monotonic `geometry_revision`.
- Geometry revision increments only when geometry content changes.
- At most one non-archived active Site may exist per Project, enforced in service logic and by a PostgreSQL partial unique index.
- Archived active Sites auto-deactivate; archived Sites cannot activate without explicit restore.
- Cross-owner requests are indistinguishable from missing Projects; a Site ID cannot be reused under another Project.
- GiST index exists on Site geometry for future deterministic spatial operations.
- Alembic head is exactly `0004`.
- Full backend regression suite passes 54/54.
- No Git commit has been created.

## TASK-010 acceptance evidence
- Centralized owner-scoped Project resolution and Project+Site identity resolution are now reusable architecture boundaries.
- Analysis scope requires an owned, non-archived Project and an active, non-archived Site.
- Foreign Project IDs remain indistinguishable from missing IDs.
- Site IDs cannot be substituted across Projects, including Projects owned by the same user.
- Audit/read state and evidence-producing analysis state are explicitly separated.
- Existing Project/Site services now use the centralized isolation resolver.
- No migration was required; Alembic head remains `0004`.
- Full backend regression suite passes 63/63.
- No Git commit has been created.

## TASK-011 acceptance evidence
- Dedicated authenticated active-Site endpoint keeps active context server-owned.
- MapLibre source/layers consume the exact server-returned MultiPolygon geometry.
- Geometry hash and geometry revision remain visible map provenance; client bounds are presentation-only.
- Explicit unauthenticated, no-active-Site, API error and degraded map states are implemented.
- Full backend regression suite passes 66/66.
- No migration was required; Alembic head remains `0004`.
- npm registry remains unavailable in the ChatGPT runtime, so frontend dependency-backed typecheck/test/lint/build and browser WebGL acceptance remain pending.
- No Git commit has been created.

## Runtime gates still pending on the owner's machine
- Docker Compose service startup.
- PostgreSQL/PostGIS/pgvector live readiness.
- Live `alembic upgrade head` against the persistent PostgreSQL service, including TASK-009 native geometry constraints/indexes.
- TASK-005 npm dependency-backed frontend typecheck/test/lint/build.

## Next task
TASK-012 — GIS Layer Model.

## TASK-012 through TASK-019 rebuild state
- TASK-012 — PASS — GIS Layer Model
- TASK-013 — PASS — GIS Feature Ingestion
- TASK-014 — PASS — Deterministic GIS Analysis
- TASK-015 — PASS — GeometryReference
- TASK-016 — PASS — MapAction Service
- TASK-017 — PASS — PlanningDocument Model
- TASK-018 — PASS — PDF Ingestion / page-level extraction
- TASK-019 — PASS — Deterministic Document Chunking

## TASK-019 acceptance evidence
- `DocumentChunk` persists exact page-local source lineage: DocumentVersion, DocumentPage, page number, chunk index/sequence and source character offsets.
- Chunk text is the exact substring of persisted page extraction for the recorded `[start_char:end_char]` range.
- Each chunk carries SHA-256 text identity, deterministic UUIDv5 identity and explicit `chunker_version`.
- Rebuilding the same source with the same configuration reproduces the same chunk identities.
- Chunking never crosses a page boundary; blank/failed/OCR-required pages are skipped and remain review-visible.
- Bounded server chunking configuration: max 256–8000 chars; overlap must be nonnegative, below max and no more than 50% of max.
- Rebuilding chunks resets `DocumentVersion.index_state` to `pending`; TASK-020 owns embeddings/indexing.
- Cross-owner and cross-project chunk build/list access fails closed through existing PlanningDocument isolation.
- Alembic head is exactly `0009`; migration 0009 adds `document_chunks` only and no embedding/vector payload.
- Full backend regression suite passes 148/148.
- No Git commit has been created.

## Next task
TASK-020 — Embedding / Index Pipeline.

## TASK-020 acceptance evidence
- Server-owned embedding provider registry supports Ollama primary and OpenAI fallback/configurable execution; clients cannot supply arbitrary provider URLs or credentials.
- Ollama uses its current `/api/embed` batch interface; OpenAI uses the configured `/v1/embeddings` compatible endpoint.
- `DocumentEmbeddingIndex` persists exact version/provider/model/revision/dimension lineage and build state.
- `DocumentChunkEmbedding` persists exact chunk ID + text SHA-256 alongside a native PostgreSQL `vector` payload.
- Stable UUIDv5 identities are derived from the immutable version/provider/model/dimension signature and exact chunk lineage.
- A ready index is reused only when the persisted `(chunk_id, text_sha256)` set exactly equals the current chunk lineage; stale embeddings are rebuilt rather than silently reused.
- Malformed counts, inconsistent dimensions, non-numeric/non-finite vectors and provider exhaustion fail closed; version index state becomes `failed` on provider/index validation failure.
- `DocumentVersion.index_state` becomes `ready` only after all current chunks have validated embeddings.
- No HNSW/IVFFlat or hybrid ranking is introduced yet; TASK-021 owns retrieval/ranking.
- Alembic head is exactly `0010`; offline PostgreSQL SQL emits native `embedding vector NOT NULL`.
- Full backend regression suite passes 160/160.
- No Git commit has been created.

## Next task
TASK-021 — Hybrid Retrieval.

## TASK-021 implementation
- Project-scoped document retrieval combines keyword and vector candidate ranks using deterministic Reciprocal Rank Fusion (RRF, k=60).
- PostgreSQL production keyword arm uses `websearch_to_tsquery('simple', ...)` and `ts_rank_cd`; pgvector arm uses exact cosine distance `<=>`.
- SQLite test path mirrors deterministic keyword/cosine behavior without pretending to validate PostgreSQL execution.
- Vector queries must match persisted embedding provider/model/dimension lineage; failures are surfaced and retrieval degrades explicitly to keyword-only.
- Every hit returns exact Project → PlanningDocument → DocumentVersion → DocumentPage → DocumentChunk identities plus page number and source/chunk checksums.
- Archived PlanningDocuments and out-of-project resources are excluded/fail closed.
- No HNSW/IVFFlat migration and no citation presentation layer are introduced in TASK-021.

## TASK-021 acceptance evidence
- Project-scoped hybrid document retrieval is implemented at `POST /api/v1/projects/{project_id}/document-search`.
- PostgreSQL keyword arm uses `websearch_to_tsquery('simple', ...)` + `ts_rank_cd`; vector arm uses exact pgvector cosine distance `<=>`.
- Candidate ranks are fused deterministically with Reciprocal Rank Fusion (RRF, k=60) and stable chunk-ID tie breaking.
- Every hit preserves exact Project → PlanningDocument → DocumentVersion → DocumentPage → DocumentChunk lineage, page number, version checksum and chunk text checksum.
- Vector retrieval is allowed only while the DocumentVersion remains `index_state=ready`; stale embedding rows whose text SHA-256 no longer matches the current chunk are excluded.
- Query embeddings must match persisted provider/model/revision/dimensions. Provider failure or absent ready indexes is surfaced as explicit keyword-only degradation.
- Archived documents, cross-owner projects and requested filters fail closed/exclude evidence as appropriate.
- No migration was needed; Alembic head remains `0010`. No HNSW/IVFFlat index or citation presentation layer was introduced.
- Full backend regression suite reports 170/170 tests passed. The surrounding shell command reached its environment timeout after pytest had already printed the complete passing result.
- No Git commit has been created.

## Next task
TASK-022 — Citation / Provenance Engine.

## TASK-022 — PASS — Citation / Provenance Engine
- Retrieval hits now include `document_citation.v1` references and human-readable citation labels.
- Citation references bind exact project, document, version, page and chunk identities plus version/page/chunk SHA-256 lineage.
- `POST /api/v1/projects/{project_id}/citations/resolve` re-resolves authoritative text/metadata server-side; client-supplied text is never accepted.
- Resolver validates active project ownership, archived/source state, extraction/readability state, exact lineage IDs/hashes, recomputed SHA-256 text identities and exact chunk-to-page character range.
- Cross-project/cross-owner replay, stale/tampered references, duplicate chunk references and archived sources fail closed.
- Citation provenance explicitly does not prove policy applicability; unreviewed/requires-review states remain surfaced as limitations.
- No migration required; Alembic head remains `0010`.
- Full backend regression suite passes 182/182 (97 + 85 split to avoid environment timeout).
- No Git commit has been created.

## Next task
TASK-023 — PolicyReference Workflow.

## TASK-023 — PASS — PolicyReference Workflow
- `PolicyReference` is now the reviewed, project-scoped representation layer between validated document citations and future deterministic policy criteria.
- Candidate creation requires a validated `document_citation.v1`; authoritative `source_wording` is copied from the server-resolved chunk rather than accepted from the client.
- Exact Document/Version/Page/Chunk IDs plus version/page/chunk SHA-256 lineage are persisted with document-class and authority snapshots.
- Candidate records begin as `draft + unreviewed + applicability unassessed`; retrieval matches are never silently promoted to policy truth.
- Explicit review actions support `verify`, `reject`, and `requires_review`, with reviewer identity/time persisted.
- Verification re-resolves the source citation and rejects stale/unavailable/tampered evidence before promotion.
- Only `final + verified + non-archived` PolicyReference records can resolve for downstream evidence use.
- Final policy content is immutable; rejected records remain auditable but unusable as policy evidence.
- Applicability is kept distinct from source-grounded interpretation and may remain unassessed/limited/requires-review.
- Downstream resolution explicitly states that verification is not statutory approval, legal certification, planning permission, or automatic site applicability.
- Alembic head is exactly `0011`; migration 0011 creates `policy_references` with exact source FKs and state-consistency constraints.
- Focused TASK-023/Citation/migration suite passes 25/25.
- Full backend regression suite passes 195/195 (100 + 95 split).
- Python compile and offline PostgreSQL upgrade/downgrade gates pass.
- No Git commit has been created.

## Next task
TASK-024 — PolicyCriterion Domain.

## TASK-024 — PASS — PolicyCriterion Domain
- `PolicyCriterion` now represents reviewed deterministic policy rules linked to an exact verified `PolicyReference`.
- Creation requires the parent PolicyReference to remain final, verified, non-archived and source-resolvable.
- Supported typed rule families are numeric, text, boolean, set and manual-review with constrained operators.
- Numeric thresholds/range bounds must be explicitly present in exact `source_evidence_text` from the verified PolicyReference; arbitrary/fabricated numbers are rejected.
- Text/set expected values must be source-grounded; boolean mappings require explicit interpretation notes.
- Criteria start `draft + unreviewed`; only explicit review can produce `final + verified` deterministic-use records.
- Verification re-resolves the parent PolicyReference and revalidates source grounding.
- Final criterion content is immutable; rejected/archived criteria cannot resolve for deterministic use.
- Project-local criterion codes are unique.
- Alembic head is exactly `0012`; migration 0012 creates `policy_criteria` with source FK, typed rule payloads and DB consistency checks.
- Focused TASK-024 suite passes 11/11.
- Full backend regression passes 206/206 (108 + 98 split).
- Python compile and offline PostgreSQL upgrade/downgrade gates pass.
- No Git commit has been created.

## Next task
TASK-025 — ComplianceFact Domain.

## TASK-025 — PASS — ComplianceFact Domain
- `ComplianceFact` now persists project/site-scoped evidence values independently from Compliance conclusions.
- Facts support typed numeric/text/boolean/set values and explicit source classes: `user_supplied` and `gis_analysis`.
- Owner-supplied facts are labelled `owner_assertion_v1` and carry an explicit limitation that GeoPilot did not independently measure the value.
- GIS-derived facts can only be produced by server-owned TASK-014 deterministic services; the client cannot submit the authoritative GIS measurement value.
- TASK-025 persists site geometry hash/revision for every fact and GISLayer/GISFeature IDs + feature geometry hash where applicable.
- A deterministic SHA-256 provenance hash identifies the evidence payload and duplicate identical provenance is rejected.
- Fact value/source content is immutable after creation; only archive state is mutable.
- Resolve-for-use revalidates active project/site scope and exact current geometry identity; stale Site/GISFeature evidence fails closed.
- Referenced GISLayer/GISFeature FKs use ON DELETE RESTRICT to preserve durable historical evidence lineage.
- A validated fact is explicitly evidence only and never a ComplianceFinding, statutory conclusion, legal compliance statement, or development approval.
- Alembic head is exactly `0013`; migration 0013 creates `compliance_facts` with payload/source/provenance constraints.
- Focused TASK-025 suite passes 14/14.
- Full backend regression passes 220/220 (111 + 109 split).
- Python compile and offline PostgreSQL upgrade/downgrade gates pass.
- No Git commit has been created.

## Next task
TASK-026 — Deterministic Compliance Engine.

## Rebuild completion update — 14 Aug 2026

TASK-026 through TASK-044 implementation has been completed in the clean-room rebuild.

- TASK-026 Deterministic Compliance Engine — PASS
- TASK-027 ComplianceRun / ComplianceFinding persistence — PASS
- TASK-028 SuitabilityProfile domain — PASS
- TASK-029 SuitabilityCriterion domain — PASS
- TASK-030 Deterministic Suitability engine — PASS
- TASK-031 RasterDataset domain — PASS
- TASK-032 Raster processing foundation — PASS
- TASK-033 Satellite provider framework — PASS
- TASK-034 ToolEvidence contract — PASS
- TASK-035 Integrated planning foundation — PASS
- TASK-036 AI Planning Workspace implementation — PASS (frontend executable npm gates pending local/npm connectivity)
- TASK-037 PlanningRun orchestration — PASS
- TASK-038 Server-owned ToolRegistry — PASS
- TASK-039 Map-linked evidence foundation — PASS
- TASK-040 Planning intelligence / grounded synthesis — PASS
- TASK-041 truthful Compliance/Suitability acceptance gate — PASS; real-data acceptance remains data-dependent and must not be fabricated
- TASK-042 Satellite Temporal Intelligence implementation — PASS; legitimate real imagery/professional acceptance remains data-dependent
- TASK-043 Report Composition / Professional Review — PASS
- TASK-044 Provider Resilience / Golden Path — PASS

Current Alembic head: `0020`.
Backend regression: 238/238 tests PASS across three batches.
Full offline PostgreSQL migration generation: PASS (`0001` through `0020`).
Git commits: 0 by owner decision.

Outstanding runtime gates are environmental rather than silently treated as passed: Docker/PostgreSQL live migration and browser acceptance must be run on the owner's Windows laptop; frontend npm dependency install/typecheck/test/lint/build could not execute in the ChatGPT build runtime because npm installation timed out.

### Track B AI intelligence checkpoint
- Added persisted `location_type` and `data_stage` to Track B temporal analysis manifests.
- Added grounded Urban vs Rural Planning Intelligence comparison service/API.
- Comparison requires explicit urban + rural analyses and closed organizer evidence.
- Numeric hallucination guard covers comparative AI narrative.
- Track B focused suite: 12 passed.
- Full backend regression was started and reached 100+ passing tests without a failure before the execution window timed out; final uninterrupted full-suite certification remains pending.

### Track B Planner Decision Workspace checkpoint
- Added a dedicated AI decision-workspace contract/API for a single temporal analysis.
- Planner can submit a problem/question; AI answers only from organizer-derived deterministic evidence.
- Output is structured as Issue → Evidence → non-statutory triage priority → Planning implication → Recommended actions → Verification need → Limitations.
- Added strict evidence-reference allowlist and numeric hallucination guard for decision briefs.
- Planner decision packet persists alongside the analysis and is included in the evidence PDF when present.
- Frontend adds a futuristic decision-support workspace with priority, evidence, action queue, verification needs, and professional-review boundary.


## Track B Final Judging Hardening v6
- Added a dedicated Judge View to the Track B Command Center.
- Judge View performs client-side mission readiness preflight for organizer-only Urban and Rural T1/T2 pairs sharing Site and data stage.
- Completed mission results are compressed into a one-screen decision deck: Urban change, Rural change, AI planning priority, evidence boundary and professional-review status.
- Judge View never changes analysis semantics and does not bypass the organizer-only evidence gate.

## TRACK B V7 — COMPETITION ACCEPTANCE GATE
- Added server-side Track B readiness endpoint with explicit READY/PARTIAL/BLOCKED state.
- Acceptance checks cover competition mode, GTiff/JP2 runtime, Urban/Rural T1/T2 pairing, local artifact/checksum lineage, temporal metadata, and planning-AI configuration.
- Synthetic QA fixtures are blocked from Hackathon Mission auto-pairing.
- Added local B04/B08 Urban/Rural T1/T2 synthetic fixture generator for engineering acceptance only; generated artifacts carry an explicit NOT ORGANIZER EVIDENCE warning.
- Track B focused regression: 20 passed.
- Backend compile-all: passed.
- Full-suite run in this environment exceeded execution window before summary; no new failure was observed before timeout. Previous v5 checkpoint had 265/265 backend tests passing.
- Frontend full typecheck/build remains environment-blocked because package dependencies are not installed in this runtime; global TypeScript invocation confirms the blocker is missing vitest/testing-library type packages, not a reported Track B source error.
- OCR migration 0021 remains intentionally HOLD and is not part of Track B v7.
