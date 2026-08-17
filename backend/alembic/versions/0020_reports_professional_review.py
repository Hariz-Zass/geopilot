"""report composition and professional review"""
from alembic import op
import sqlalchemy as sa
revision='0020'; down_revision='0019'; branch_labels=None; depends_on=None
def upgrade():
 op.create_table('planning_reports',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('project_id',sa.Uuid(),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False),sa.Column('site_id',sa.Uuid(),sa.ForeignKey('sites.id',ondelete='RESTRICT'),nullable=False),sa.Column('planning_run_id',sa.Uuid(),sa.ForeignKey('planning_runs.id',ondelete='RESTRICT'),nullable=False),sa.Column('created_by_user_id',sa.Uuid(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),sa.Column('title',sa.String(255),nullable=False),sa.Column('status',sa.String(32),nullable=False),sa.Column('report_json',sa.JSON(),nullable=False),sa.Column('file_path',sa.Text()),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
 op.create_table('professional_reviews',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('project_id',sa.Uuid(),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False),sa.Column('planning_run_id',sa.Uuid(),sa.ForeignKey('planning_runs.id',ondelete='RESTRICT'),nullable=False),sa.Column('reviewer_user_id',sa.Uuid(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),sa.Column('decision',sa.String(32),nullable=False),sa.Column('notes',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
def downgrade(): op.drop_table('professional_reviews'); op.drop_table('planning_reports')
