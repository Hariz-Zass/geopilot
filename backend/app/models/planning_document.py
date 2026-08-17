from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import VectorType


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlanningDocument(Base):
    __tablename__ = "planning_documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_class: Mapped[str] = mapped_column(String(32), nullable=False)
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geographic_applicability: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    project = relationship("Project", back_populates="planning_documents")
    versions = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentVersion.version_sequence",
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_sequence", name="uq_document_versions_document_sequence"),
        UniqueConstraint("document_id", "checksum_sha256", name="uq_document_versions_document_checksum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("planning_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False, default="application/pdf")
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ingestion_state: Mapped[str] = mapped_column(String(32), nullable=False, default="registered")
    extraction_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    index_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    review_state: Mapped[str] = mapped_column(String(32), nullable=False, default="unreviewed")
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    document = relationship("PlanningDocument", back_populates="versions")
    pages = relationship(
        "DocumentPage",
        back_populates="document_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentPage.page_number",
    )
    chunks = relationship(
        "DocumentChunk",
        back_populates="document_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentChunk.chunk_sequence",
    )
    embedding_indexes = relationship(
        "DocumentEmbeddingIndex",
        back_populates="document_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_version_id", "page_number", name="uq_document_pages_version_page"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extraction_method: Mapped[str] = mapped_column(String(32), nullable=False, default="pypdf_text")
    extraction_state: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    requires_ocr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    document_version = relationship("DocumentVersion", back_populates="pages")
    chunks = relationship(
        "DocumentChunk",
        back_populates="document_page",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentChunk.chunk_index",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_page_id", "chunk_index", name="uq_document_chunks_page_index"),
        UniqueConstraint("document_version_id", "chunk_sequence", name="uq_document_chunks_version_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_page_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(64), nullable=False)
    max_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    overlap_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    document_version = relationship("DocumentVersion", back_populates="chunks")
    document_page = relationship("DocumentPage", back_populates="chunks")
    embeddings = relationship(
        "DocumentChunkEmbedding",
        back_populates="document_chunk",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentEmbeddingIndex(Base):
    __tablename__ = "document_embedding_indexes"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id", "provider", "model_name", "model_revision",
            name="uq_document_embedding_indexes_version_provider_model_revision",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_revision: Mapped[str] = mapped_column(String(255), nullable=False, default="unspecified")
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="building")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document_version = relationship("DocumentVersion", back_populates="embedding_indexes")
    chunk_embeddings = relationship(
        "DocumentChunkEmbedding",
        back_populates="embedding_index",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentChunkEmbedding(Base):
    __tablename__ = "document_chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("embedding_index_id", "document_chunk_id", name="uq_document_chunk_embeddings_index_chunk"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    embedding_index_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_embedding_indexes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VectorType(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    embedding_index = relationship("DocumentEmbeddingIndex", back_populates="chunk_embeddings")
    document_chunk = relationship("DocumentChunk", back_populates="embeddings")
