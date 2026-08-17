from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

def utcnow(): return datetime.now(timezone.utc)

class RasterDataset(Base):
    __tablename__='raster_datasets'
    __table_args__=(
        CheckConstraint("source_kind IN ('upload','satellite_acquired','external_reference')",name='raster_source_kind_valid'),
        CheckConstraint("status IN ('registered','ready','invalid','archived')",name='raster_status_valid'),
    )
    id:Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    project_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('projects.id',ondelete='CASCADE'),nullable=False,index=True)
    site_id:Mapped[uuid.UUID|None]=mapped_column(Uuid,ForeignKey('sites.id',ondelete='RESTRICT'),index=True)
    created_by_user_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    name:Mapped[str]=mapped_column(String(255),nullable=False)
    source_kind:Mapped[str]=mapped_column(String(32),nullable=False)
    provider:Mapped[str|None]=mapped_column(String(80)); collection:Mapped[str|None]=mapped_column(String(120)); scene_id:Mapped[str|None]=mapped_column(String(255)); acquisition_datetime:Mapped[str|None]=mapped_column(String(64))
    crs:Mapped[str]=mapped_column(String(80),nullable=False); width:Mapped[int]=mapped_column(nullable=False); height:Mapped[int]=mapped_column(nullable=False); band_count:Mapped[int]=mapped_column(nullable=False); band_names:Mapped[list]=mapped_column(JSON,nullable=False,default=list); pixel_size:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict); bounds:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict); nodata:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
    source_uri:Mapped[str|None]=mapped_column(Text); checksum_sha256:Mapped[str]=mapped_column(String(64),nullable=False,index=True); provenance:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict); status:Mapped[str]=mapped_column(String(24),nullable=False,default='registered'); is_archived:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)
