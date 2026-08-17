"""planning run orchestration"""
from alembic import op
import sqlalchemy as sa
revision='0019'; down_revision='0018'; branch_labels=None; depends_on=None
def upgrade():
 op.create_table('planning_runs',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('project_id',sa.Uuid(),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False),sa.Column('site_id',sa.Uuid(),sa.ForeignKey('sites.id',ondelete='RESTRICT'),nullable=False),sa.Column('created_by_user_id',sa.Uuid(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),sa.Column('question',sa.Text(),nullable=False),sa.Column('development_intent',sa.Text()),sa.Column('status',sa.String(48),nullable=False),sa.Column('plan',sa.JSON(),nullable=False),sa.Column('evidence',sa.JSON(),nullable=False),sa.Column('findings',sa.JSON(),nullable=False),sa.Column('limitations',sa.JSON(),nullable=False),sa.Column('provider_metadata',sa.JSON(),nullable=False),sa.Column('synthesis',sa.Text()),sa.Column('review_state',sa.String(32),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
def downgrade(): op.drop_table('planning_runs')
