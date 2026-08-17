from __future__ import annotations
import uuid
from datetime import datetime,timezone
from sqlalchemy import DateTime,ForeignKey,JSON,String,Text,Uuid
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base

def utcnow(): return datetime.now(timezone.utc)
class PlanningReport(Base):
 __tablename__='planning_reports'; id:Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4); project_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('projects.id',ondelete='CASCADE'),nullable=False,index=True); site_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('sites.id',ondelete='RESTRICT'),nullable=False); planning_run_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('planning_runs.id',ondelete='RESTRICT'),nullable=False,index=True); created_by_user_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('users.id',ondelete='RESTRICT'),nullable=False); title:Mapped[str]=mapped_column(String(255),nullable=False); status:Mapped[str]=mapped_column(String(32),nullable=False,default='draft'); report_json:Mapped[dict]=mapped_column(JSON,nullable=False); file_path:Mapped[str|None]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
class ProfessionalReview(Base):
 __tablename__='professional_reviews'; id:Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4); project_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('projects.id',ondelete='CASCADE'),nullable=False,index=True); planning_run_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('planning_runs.id',ondelete='RESTRICT'),nullable=False,index=True); reviewer_user_id:Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('users.id',ondelete='RESTRICT'),nullable=False); decision:Mapped[str]=mapped_column(String(32),nullable=False); notes:Mapped[str]=mapped_column(Text,nullable=False); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
