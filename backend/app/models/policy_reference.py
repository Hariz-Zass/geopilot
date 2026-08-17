from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PolicyReference(Base):
    __tablename__ = "policy_references"
    __table_args__ = (
        CheckConstraint("page_number >= 1", name="policy_reference_page_number_valid"),
        CheckConstraint("representation_state IN ('draft','final')", name="policy_reference_representation_state_valid"),
        CheckConstraint("review_state IN ('unreviewed','requires_review','verified','rejected')", name="policy_reference_review_state_valid"),
        CheckConstraint("applicability_status IN ('unassessed','requires_review','applicable','not_applicable','limited')", name="policy_reference_applicability_status_valid"),
        CheckConstraint(
            "(representation_state = 'draft' AND review_state IN ('unreviewed','requires_review')) OR "
            "(representation_state = 'final' AND review_state IN ('verified','rejected'))",
            name="policy_reference_final_review_consistency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("planning_documents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_page_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_pages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_chunks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_class_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    authority_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_wording: Mapped[str] = mapped_column(Text, nullable=False)
    policy_statement: Mapped[str] = mapped_column(Text, nullable=False)

    representation_state: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    review_state: Mapped[str] = mapped_column(String(24), nullable=False, default="unreviewed")
    applicability_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unassessed")
    applicability_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
