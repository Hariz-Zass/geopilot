from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.planning_document import DocumentChunk, DocumentPage, DocumentVersion
from app.models.user import User
from app.services.planning_documents import (
    DocumentVersionNotFoundError,
    PlanningDocumentNotFoundError,
    PlanningDocumentProjectNotFoundError,
    PlanningDocumentStateError,
    get_document_version,
    get_planning_document,
)

CHUNKER_VERSION = "page_chars_v1"
CHUNK_UUID_NAMESPACE = uuid.UUID("c4ba57f9-b7bd-4e6e-921f-72499d365f42")


class DocumentChunkingStateError(Exception):
    pass


class DocumentChunkingConfigError(Exception):
    pass


@dataclass(frozen=True)
class ChunkBuildSummary:
    version: DocumentVersion
    chunk_count: int
    chunked_page_count: int
    skipped_page_count: int
    max_chars: int
    overlap_chars: int
    chunker_version: str = CHUNKER_VERSION


def _choose_end(text: str, start: int, max_chars: int) -> int:
    hard_end = min(len(text), start + max_chars)
    if hard_end == len(text):
        return hard_end

    # Prefer a natural whitespace boundary near the end of the target window,
    # but never shrink below 60% of max_chars solely to find one.
    floor = start + max(1, int(max_chars * 0.60))
    cursor = hard_end
    while cursor > floor and not text[cursor - 1].isspace():
        cursor -= 1
    if cursor > floor:
        return cursor
    return hard_end


def _page_windows(text: str, *, max_chars: int, overlap_chars: int) -> list[tuple[int, int, str]]:
    if not text:
        return []
    windows: list[tuple[int, int, str]] = []
    start = 0
    while start < len(text):
        end = _choose_end(text, start, max_chars)
        if end <= start:
            raise RuntimeError("chunker failed to advance")
        chunk_text = text[start:end]
        windows.append((start, end, chunk_text))
        if end >= len(text):
            break
        next_start = max(0, end - overlap_chars)
        if next_start <= start:
            next_start = end
        start = next_start
    return windows


def _deterministic_chunk_id(
    *, page_id: uuid.UUID, chunk_index: int, start_char: int, end_char: int, text_sha256: str
) -> uuid.UUID:
    identity = f"{CHUNKER_VERSION}:{page_id}:{chunk_index}:{start_char}:{end_char}:{text_sha256}"
    return uuid.uuid5(CHUNK_UUID_NAMESPACE, identity)


def build_document_chunks(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    max_chars: int = 1200,
    overlap_chars: int = 200,
) -> ChunkBuildSummary:
    if max_chars < 256 or max_chars > 8000:
        raise DocumentChunkingConfigError("max_chars must be between 256 and 8000")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise DocumentChunkingConfigError("overlap_chars must be nonnegative and smaller than max_chars")
    if overlap_chars > max_chars // 2:
        raise DocumentChunkingConfigError("overlap_chars must not exceed half of max_chars")

    document = get_planning_document(
        session, owner=owner, project_id=project_id, document_id=document_id
    )
    if document.is_archived:
        raise PlanningDocumentStateError("archived planning document cannot be chunked")
    version = get_document_version(
        session,
        owner=owner,
        project_id=project_id,
        document_id=document_id,
        version_id=version_id,
    )
    if version.ingestion_state != "available":
        raise DocumentChunkingStateError("document version source is not available")
    if version.extraction_state not in {"ready", "requires_review"}:
        raise DocumentChunkingStateError("document version extraction is not ready for chunking")

    pages = list(
        session.scalars(
            select(DocumentPage)
            .where(DocumentPage.document_version_id == version.id)
            .order_by(DocumentPage.page_number.asc(), DocumentPage.id.asc())
        )
    )
    if not pages:
        raise DocumentChunkingStateError("document version has no extracted pages")

    prepared: list[DocumentChunk] = []
    sequence = 0
    chunked_pages = 0
    skipped_pages = 0
    for page in pages:
        if page.extraction_state != "ready" or not page.extracted_text:
            skipped_pages += 1
            continue
        page_windows = _page_windows(
            page.extracted_text,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
        if page_windows:
            chunked_pages += 1
        for chunk_index, (start, end, text) in enumerate(page_windows):
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            prepared.append(
                DocumentChunk(
                    id=_deterministic_chunk_id(
                        page_id=page.id,
                        chunk_index=chunk_index,
                        start_char=start,
                        end_char=end,
                        text_sha256=digest,
                    ),
                    document_version_id=version.id,
                    document_page_id=page.id,
                    page_number=page.page_number,
                    chunk_index=chunk_index,
                    chunk_sequence=sequence,
                    start_char=start,
                    end_char=end,
                    text=text,
                    text_sha256=digest,
                    chunker_version=CHUNKER_VERSION,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
            )
            sequence += 1

    if not prepared:
        raise DocumentChunkingStateError("document version contains no chunkable extracted text")

    session.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id == version.id))
    session.add_all(prepared)

    provenance = dict(version.provenance or {})
    provenance["chunking"] = {
        "chunker_version": CHUNKER_VERSION,
        "max_chars": max_chars,
        "overlap_chars": overlap_chars,
        "chunk_count": len(prepared),
        "chunked_page_count": chunked_pages,
        "skipped_page_count": skipped_pages,
    }
    version.provenance = provenance
    # TASK-020 owns embeddings/indexing. Rebuilding chunks invalidates any future index.
    version.index_state = "pending"
    session.commit()
    session.refresh(version)

    return ChunkBuildSummary(
        version=version,
        chunk_count=len(prepared),
        chunked_page_count=chunked_pages,
        skipped_page_count=skipped_pages,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )


def list_document_chunks(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    page_number: int | None = None,
) -> list[DocumentChunk]:
    get_document_version(
        session,
        owner=owner,
        project_id=project_id,
        document_id=document_id,
        version_id=version_id,
    )
    stmt = select(DocumentChunk).where(DocumentChunk.document_version_id == version_id)
    if page_number is not None:
        stmt = stmt.where(DocumentChunk.page_number == page_number)
    return list(session.scalars(stmt.order_by(DocumentChunk.chunk_sequence.asc())))
