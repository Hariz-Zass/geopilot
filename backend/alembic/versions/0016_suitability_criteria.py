"""suitability criteria"""
from alembic import op
import sqlalchemy as sa
revision='0016'; down_revision='0015'; branch_labels=None; depends_on=None
def upgrade():
 op.create_table('suitability_criteria',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('profile_id',sa.Uuid(),sa.ForeignKey('suitability_profiles.id',ondelete='CASCADE'),nullable=False),sa.Column('project_id',sa.Uuid(),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False),sa.Column('label',sa.String(255),nullable=False),sa.Column('metric_key',sa.String(160),nullable=False),sa.Column('factor_type',sa.String(24),nullable=False),sa.Column('operator',sa.String(24),nullable=False),sa.Column('weight',sa.Numeric(8,4),nullable=False),sa.Column('threshold_numeric',sa.Numeric(24,8)),sa.Column('expected_value',sa.Text()),sa.Column('evidence_source',sa.String(32),nullable=False),sa.Column('policy_reference_id',sa.Uuid(),sa.ForeignKey('policy_references.id',ondelete='RESTRICT')),sa.Column('compliance_fact_id',sa.Uuid(),sa.ForeignKey('compliance_facts.id',ondelete='RESTRICT')),sa.Column('gis_feature_id',sa.Uuid(),sa.ForeignKey('gis_features.id',ondelete='RESTRICT')),sa.Column('review_state',sa.String(24),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
def downgrade(): op.drop_table('suitability_criteria')
