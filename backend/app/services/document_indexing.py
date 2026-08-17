from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.planning_document import DocumentChunk, DocumentChunkEmbedding, DocumentEmbeddingIndex
from app.models.user import User
from app.services.embedding_providers import EmbeddingBatch, EmbeddingProviderError, embed_with_fallback
from app.services.planning_documents import get_document_version

INDEX_NAMESPACE = uuid.UUID("db9b4d18-b950-4cd7-becf-263996768ff4")
EMBEDDING_NAMESPACE = uuid.UUID("3f2d80c8-1410-4f62-bfd2-115a5ef06c5c")


class DocumentIndexingStateError(Exception): pass
class DocumentIndexingProviderError(Exception): pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _index_id(version_id: uuid.UUID, batch: EmbeddingBatch, dimensions: int) -> uuid.UUID:
    key = f"{version_id}:{batch.provider}:{batch.model_name}:{batch.model_revision}:{dimensions}"
    return uuid.uuid5(INDEX_NAMESPACE, key)


def _embedding_id(index_id: uuid.UUID, chunk_id: uuid.UUID, text_sha256: str) -> uuid.UUID:
    return uuid.uuid5(EMBEDDING_NAMESPACE, f"{index_id}:{chunk_id}:{text_sha256}")


def build_document_embedding_index(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    force_rebuild: bool = False,
) -> DocumentEmbeddingIndex:
    version = get_document_version(session, owner=owner, project_id=project_id, document_id=document_id, version_id=version_id)
    chunks = list(session.scalars(select(DocumentChunk).where(DocumentChunk.document_version_id == version.id).order_by(DocumentChunk.chunk_sequence.asc())))
    if not chunks:
        raise DocumentIndexingStateError("document version has no chunks to index")

    try:
        batch = embed_with_fallback([chunk.text for chunk in chunks])
    except EmbeddingProviderError as exc:
        version.index_state = "failed"
        session.commit()
        raise DocumentIndexingProviderError(str(exc)) from exc

    if len(batch.vectors) != len(chunks):
        version.index_state = "failed"
        session.commit()
        raise DocumentIndexingProviderError("embedding provider result count does not match chunk count")
    dimensions = len(batch.vectors[0]) if batch.vectors else 0
    if not 1 <= dimensions <= 4096 or any(len(vector) != dimensions for vector in batch.vectors):
        version.index_state = "failed"
        session.commit()
        raise DocumentIndexingProviderError("embedding dimensions are invalid or inconsistent")

    index_id = _index_id(version.id, batch, dimensions)
    existing = session.get(DocumentEmbeddingIndex, index_id)
    if existing is not None and existing.state == "ready" and not force_rebuild:
        rows = list(session.execute(
            select(DocumentChunkEmbedding.document_chunk_id, DocumentChunkEmbedding.text_sha256)
            .where(DocumentChunkEmbedding.embedding_index_id == index_id)
        ))
        persisted_lineage = {(row[0], row[1]) for row in rows}
        current_lineage = {(chunk.id, chunk.text_sha256) for chunk in chunks}
        if persisted_lineage == current_lineage:
            version.index_state = "ready"
            session.commit()
            return existing

    if existing is None:
        existing = DocumentEmbeddingIndex(
            id=index_id,
            document_version_id=version.id,
            provider=batch.provider,
            model_name=batch.model_name,
            model_revision=batch.model_revision,
            dimensions=dimensions,
            state="building",
            chunk_count=0,
        )
        session.add(existing)
        session.flush()
    else:
        session.execute(delete(DocumentChunkEmbedding).where(DocumentChunkEmbedding.embedding_index_id == existing.id))
        existing.state = "building"
        existing.chunk_count = 0
        existing.completed_at = None

    for chunk, vector in zip(chunks, batch.vectors, strict=True):
        session.add(DocumentChunkEmbedding(
            id=_embedding_id(existing.id, chunk.id, chunk.text_sha256),
            embedding_index_id=existing.id,
            document_chunk_id=chunk.id,
            text_sha256=chunk.text_sha256,
            dimensions=dimensions,
            embedding=vector,
        ))

    existing.state = "ready"
    existing.chunk_count = len(chunks)
    existing.completed_at = _utcnow()
    version.index_state = "ready"
    session.commit()
    session.refresh(existing)
    return existing


def list_document_embedding_indexes(session: Session, *, owner: User, project_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID) -> list[DocumentEmbeddingIndex]:
    version = get_document_version(session, owner=owner, project_id=project_id, document_id=document_id, version_id=version_id)
    return list(session.scalars(select(DocumentEmbeddingIndex).where(DocumentEmbeddingIndex.document_version_id == version.id).order_by(DocumentEmbeddingIndex.created_at.desc())))
