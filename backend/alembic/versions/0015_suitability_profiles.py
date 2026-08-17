"""suitability profiles"""
from alembic import op
import sqlalchemy as sa
revision='0015'; down_revision='0014'; branch_labels=None; depends_on=None
def upgrade():
 op.create_table('suitability_profiles',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('project_id',sa.Uuid(),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False),sa.Column('created_by_user_id',sa.Uuid(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),sa.Column('name',sa.String(160),nullable=False),sa.Column('description',sa.Text()),sa.Column('review_state',sa.String(24),nullable=False),sa.Column('is_archived',sa.Boolean(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint('project_id','name',name='uq_suitability_profiles_project_name'))
def downgrade(): op.drop_table('suitability_profiles')
