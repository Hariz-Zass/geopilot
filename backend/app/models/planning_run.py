from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint,DateTime,ForeignKey,JSON,String,Text,Uuid
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base

def utcnow(): return datetime.now(timezone.utc)
class PlanningRun(Base):
    __tablename__='planning_runs'
    __table_args__=(CheckConstraint("status IN ('created','clarification_required','planned','running','completed','degraded','requires_professional_review','failed')",name='planning_run_status_valid'),)
    id:Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    project_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('projects.id',ondelete='CASCADE'),nullable=False,index=True)
    site_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('sites.id',ondelete='RESTRICT'),nullable=False,index=True)
    created_by_user_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    question:Mapped[str]=mapped_column(Text,nullable=False); development_intent:Mapped[str|None]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(48),nullable=False,default='created'); plan:Mapped[list]=mapped_column(JSON,nullable=False,default=list); evidence:Mapped[list]=mapped_column(JSON,nullable=False,default=list); findings:Mapped[list]=mapped_column(JSON,nullable=False,default=list); limitations:Mapped[list]=mapped_column(JSON,nullable=False,default=list); provider_metadata:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict); synthesis:Mapped[str|None]=mapped_column(Text); review_state:Mapped[str]=mapped_column(String(32),nullable=False,default='unreviewed'); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow,nullable=False)
