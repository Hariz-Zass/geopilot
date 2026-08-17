from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

def utcnow(): return datetime.now(timezone.utc)

class ComplianceRun(Base):
    __tablename__='compliance_runs'
    __table_args__=(CheckConstraint("status IN ('completed','unresolved')", name='compliance_run_status_valid'),)
    id: Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    project_id: Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('projects.id',ondelete='CASCADE'),nullable=False,index=True)
    site_id: Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('sites.id',ondelete='RESTRICT'),nullable=False,index=True)
    created_by_user_id: Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    status: Mapped[str]=mapped_column(String(24),nullable=False)
    deterministic: Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    limitations: Mapped[list]=mapped_column(JSON,nullable=False,default=list)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)

class ComplianceFinding(Base):
    __tablename__='compliance_findings'
    __table_args__=(CheckConstraint("outcome IN ('evidence_indicates_compliance','evidence_indicates_non_compliance','unresolved')", name='compliance_finding_outcome_valid'),)
    id: Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    run_id: Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('compliance_runs.id',ondelete='CASCADE'),nullable=False,index=True)
    project_id: Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('projects.id',ondelete='CASCADE'),nullable=False,index=True)
    site_id: Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('sites.id',ondelete='RESTRICT'),nullable=False,index=True)
    policy_criterion_id: Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('policy_criteria.id',ondelete='RESTRICT'),nullable=False,index=True)
    compliance_fact_id: Mapped[uuid.UUID]=mapped_column(Uuid,ForeignKey('compliance_facts.id',ondelete='RESTRICT'),nullable=False,index=True)
    outcome: Mapped[str]=mapped_column(String(64),nullable=False)
    evaluation: Mapped[dict]=mapped_column(JSON,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)
