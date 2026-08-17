# TASK-019 — Deterministic Document Chunking

Status: PASS

## Scope
Transform persisted `DocumentPage` text into deterministic page-local chunks while preserving exact document/version/page provenance. This task intentionally does not generate embeddings or perform retrieval.

## Contract
- Chunk boundaries never cross pages.
- Stored chunk text equals the persisted page substring at `[start_char:end_char]`.
- Stable chunk identity is UUIDv5 over chunker version, page identity, chunk index, source offsets and text SHA-256.
- Chunker version: `page_chars_v1`.
- Default maximum length: 1200 characters.
- Default overlap: 200 characters.
- Bounded configuration is validated server-side.
- OCR-required/failed/empty pages are skipped rather than fabricated.
- A version with no chunkable text fails closed.
- Chunk rebuild sets `index_state=pending`; TASK-020 is responsible for embedding/index readiness.

## API
- `POST /api/v1/projects/{project_id}/documents/{document_id}/versions/{version_id}/chunks/build`
- `GET /api/v1/projects/{project_id}/documents/{document_id}/versions/{version_id}/chunks`

## Persistence
Alembic revision `0009` creates `document_chunks` with version/page lineage, ordering, character offsets, text hash and chunker configuration. It contains no embedding/vector field.

## Acceptance
- 148/148 backend tests pass.
- Python compile gate passes.
- Alembic single head is `0009`.
- Offline upgrade `0008 -> 0009` passes.
- Offline downgrade `0009 -> 0008` passes.
- Git commit count remains 0.
