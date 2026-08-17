# TASK-017 — PlanningDocument Model

Status: PASS

## Objective
Establish project-owned planning-document identity and immutable source-version lineage before extraction, OCR, page persistence, chunking, retrieval, policy interpretation, or AI synthesis.

## Implemented
- `PlanningDocument` as a project-owned logical planning source.
- Controlled document classes: RFN, RSN, RT, RKK, GPP, circular, technical guideline, local-authority source, and other controlled source.
- Authority, jurisdiction, geographic applicability, description, archive state, and timestamps.
- `DocumentVersion` as an immutable source snapshot identity with monotonically assigned per-document sequence.
- Version label, publication year/date, source kind, source filename/URI, storage URI, MIME type, file size, SHA-256 checksum, processing states, review state, provenance, and creation time.
- Unique `(document_id, version_sequence)` and `(document_id, checksum_sha256)` lineage constraints.
- Controlled upload/acquired/external-reference source identity validation.
- New version creation is rejected for archived Projects/Documents.
- Cross-owner and cross-project document/version substitution fail closed.
- Document version source identity has no PATCH/DELETE API; processing state mutation remains an internal future service concern.
- Document metadata PATCH intentionally cannot mutate document class or authority.
- Migration `0007_planning_document_domain`.

## API
- `POST /api/v1/projects/{project_id}/documents`
- `GET /api/v1/projects/{project_id}/documents`
- `GET /api/v1/projects/{project_id}/documents/{document_id}`
- `PATCH /api/v1/projects/{project_id}/documents/{document_id}`
- `POST /api/v1/projects/{project_id}/documents/{document_id}/versions`
- `GET /api/v1/projects/{project_id}/documents/{document_id}/versions`
- `GET /api/v1/projects/{project_id}/documents/{document_id}/versions/{version_id}`

## Acceptance
- Full backend regression suite: 134/134 PASS.
- Python compile gate: PASS.
- Alembic single head: `0007`.
- Offline upgrade SQL: PASS.
- Offline downgrade `0007 -> 0006`: PASS.
- `planning_documents` and `document_versions` exist in ORM metadata.
- `document_pages` and `document_chunks` do not exist yet.
- No Git commit created.

## Deferred by scope
- Binary PDF upload/storage and extraction.
- Page persistence and OCR/review workflow.
- Chunking and retrieval indexing.
- PolicyReference extraction/review.
- Controlled remote acquisition/download execution.

## Next
TASK-018 — PDF Ingestion.
