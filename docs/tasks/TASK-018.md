# TASK-018 — PDF Ingestion

Status: **PASS**

## Scope

Build the controlled PDF source-ingestion boundary on top of TASK-017 immutable DocumentVersion lineage.

## Implemented

- Added migration `0008_pdf_ingestion` and `document_pages`.
- Added persistent local document storage volume (`/data/documents`) for Docker local deployment.
- Added configurable upload limit (`DOCUMENT_UPLOAD_MAX_BYTES`, default 100 MiB).
- Manual ingestion is allowed only for registered `source_kind=upload` versions.
- Uploaded bytes must have a PDF signature and allowed MIME type.
- SHA-256 and optional byte-size metadata are verified against the immutable DocumentVersion before persistence.
- Source artifact storage paths are server-generated from UUID identities and checksum, never from client file paths.
- Page text extraction uses pypdf text-layer extraction only in v1.
- Every extracted page persists page number, exact extracted text, text SHA-256, character count, method, state, and OCR-review requirement.
- Blank/image-only pages are not treated as successfully extracted evidence: they become `empty`, `requires_ocr=true`, and the DocumentVersion moves to `requires_review`.
- Re-ingestion of an already-ingested immutable version is rejected.
- Cross-owner/project access fails closed.
- No chunk or vector-index model is introduced in this task.

## API

- `POST /api/v1/projects/{project_id}/documents/{document_id}/versions/{version_id}/ingest-pdf`
- `GET /api/v1/projects/{project_id}/documents/{document_id}/versions/{version_id}/pages`

## Acceptance

- Backend regression suite: **141/141 PASS**.
- Python compile gate: PASS.
- Alembic single head: `0008`.
- Offline upgrade `0007 -> 0008`: PASS.
- Offline downgrade `0008 -> 0007`: PASS.
- `document_pages` lineage/constraints: verified.
- `document_chunks`: absent by design.
- Git commits: 0.

## Deferred

- OCR execution is not part of TASK-018; scan/image-only pages are explicitly surfaced for review/OCR.
- Chunking is TASK-019.
- Embeddings/indexing is TASK-020.
- Live Docker/PostgreSQL smoke acceptance remains a local-runtime gate.
