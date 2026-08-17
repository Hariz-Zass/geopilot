from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PolicyCriterion(Base):
    __tablename__ = "policy_criteria"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_policy_criteria_project_code"),
        CheckConstraint("representation_state IN ('draft','final')", name="policy_criterion_representation_state_valid"),
        CheckConstraint("review_state IN ('unreviewed','requires_review','verified','rejected')", name="policy_criterion_review_state_valid"),
        CheckConstraint("value_type IN ('numeric','text','boolean','set','manual_review')", name="policy_criterion_value_type_valid"),
        CheckConstraint(
            "operator IN ('eq','ne','gt','gte','lt','lte','between','in','not_in','bool_eq','manual_review')",
            name="policy_criterion_operator_valid",
        ),
        CheckConstraint(
            "(representation_state = 'draft' AND review_state IN ('unreviewed','requires_review')) OR "
            "(representation_state = 'final' AND review_state IN ('verified','rejected'))",
            name="policy_criterion_final_review_consistency",
        ),
        CheckConstraint(
            "(value_type = 'numeric' AND operator IN ('eq','ne','gt','gte','lt','lte','between')) OR "
            "(value_type = 'text' AND operator IN ('eq','ne')) OR "
            "(value_type = 'set' AND operator IN ('in','not_in')) OR "
            "(value_type = 'boolean' AND operator = 'bool_eq') OR "
            "(value_type = 'manual_review' AND operator = 'manual_review')",
            name="policy_criterion_type_operator_consistency",
        ),
        CheckConstraint(
            "(operator = 'between' AND lower_numeric IS NOT NULL AND upper_numeric IS NOT NULL AND lower_numeric <= upper_numeric) OR "
            "(operator <> 'between')",
            name="policy_criterion_between_bounds_valid",
        ),
        CheckConstraint(
            "(value_type = 'numeric' AND ((operator = 'between' AND threshold_numeric IS NULL AND lower_numeric IS NOT NULL AND upper_numeric IS NOT NULL) OR (operator <> 'between' AND threshold_numeric IS NOT NULL AND lower_numeric IS NULL AND upper_numeric IS NULL))) OR "
            "(value_type = 'text' AND expected_text IS NOT NULL) OR "
            "(value_type = 'boolean' AND expected_boolean IS NOT NULL) OR "
            "(value_type = 'set' AND expected_values IS NOT NULL) OR "
            "(value_type = 'manual_review')",
            name="policy_criterion_payload_shape_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_reference_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("policy_references.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    code: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(160), nullable=False)
    value_type: Mapped[str] = mapped_column(String(24), nullable=False)
    operator: Mapped[str] = mapped_column(String(24), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(80), nullable=True)

    threshold_numeric: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    lower_numeric: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    upper_numeric: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    expected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    expected_values: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    source_evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    interpretation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicability_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    representation_state: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    review_state: Mapped[str] = mapped_column(String(24), nullable=False, default="unreviewed")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
