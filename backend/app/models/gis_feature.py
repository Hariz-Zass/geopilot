from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.spatial import Geometry4326


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GISFeature(Base):
    __tablename__ = "gis_features"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    layer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("gis_layers.id", ondelete="CASCADE"), nullable=False, index=True)
    source_feature_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    geometry: Mapped[str] = mapped_column(Geometry4326(), nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    geometry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    layer = relationship("GISLayer", back_populates="features")
