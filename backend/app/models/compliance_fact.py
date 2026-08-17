from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ComplianceFact(Base):
    """Persisted, project/site-scoped evidence value consumed by Compliance.

    A ComplianceFact is evidence, not a compliance conclusion.  Its source_kind
    explicitly distinguishes owner assertions from server-derived GIS
    measurements, and immutable provenance fields allow later deterministic
    engines to reject stale evidence.
    """

    __tablename__ = "compliance_facts"
    __table_args__ = (
        CheckConstraint(
            "value_type IN ('numeric','text','boolean','set')",
            name="compliance_fact_value_type_valid",
        ),
        CheckConstraint(
            "source_kind IN ('user_supplied','gis_analysis')",
            name="compliance_fact_source_kind_valid",
        ),
        CheckConstraint(
            "(value_type = 'numeric' AND numeric_value IS NOT NULL AND text_value IS NULL AND boolean_value IS NULL AND set_value IS NULL) OR "
            "(value_type = 'text' AND numeric_value IS NULL AND text_value IS NOT NULL AND boolean_value IS NULL AND set_value IS NULL) OR "
            "(value_type = 'boolean' AND numeric_value IS NULL AND text_value IS NULL AND boolean_value IS NOT NULL AND set_value IS NULL) OR "
            "(value_type = 'set' AND numeric_value IS NULL AND text_value IS NULL AND boolean_value IS NULL AND set_value IS NOT NULL)",
            name="compliance_fact_payload_shape_valid",
        ),
        CheckConstraint(
            "(source_kind = 'user_supplied' AND source_method = 'owner_assertion_v1') OR "
            "(source_kind = 'gis_analysis' AND source_method = 'postgis-geography-v1')",
            name="compliance_fact_source_method_valid",
        ),
        CheckConstraint(
            "(source_gis_feature_id IS NULL AND source_gis_layer_id IS NULL AND source_feature_geometry_hash IS NULL) OR "
            "(source_gis_feature_id IS NOT NULL AND source_gis_layer_id IS NOT NULL AND source_feature_geometry_hash IS NOT NULL)",
            name="compliance_fact_feature_lineage_complete",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    metric_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    value_type: Mapped[str] = mapped_column(String(24), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    boolean_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    set_value: Mapped[list[str] | None] = mapped_column(JSON(none_as_null=True), nullable=True)

    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_method: Mapped[str] = mapped_column(String(80), nullable=False)
    source_description: Mapped[str] = mapped_column(Text, nullable=False)
    source_details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    site_geometry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    site_geometry_revision: Mapped[int] = mapped_column(nullable=False)
    source_gis_layer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("gis_layers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_gis_feature_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("gis_features.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_feature_geometry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    provenance_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
