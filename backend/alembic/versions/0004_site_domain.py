"""project-owned site geometry domain

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.spatial import MultiPolygon4326

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("geometry", MultiPolygon4326(), nullable=False),
        sa.Column("geometry_hash", sa.String(length=64), nullable=False),
        sa.Column("geometry_revision", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_sites_project_id_projects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sites")),
    )
    op.create_index(op.f("ix_sites_project_id"), "sites", ["project_id"], unique=False)
    op.execute("CREATE INDEX ix_sites_geometry_gist ON sites USING GIST (geometry)")
    op.execute("CREATE UNIQUE INDEX uq_sites_one_active_per_project ON sites (project_id) WHERE is_active AND NOT is_archived")
    op.execute("ALTER TABLE sites ADD CONSTRAINT ck_sites_geometry_valid CHECK (ST_IsValid(geometry) AND NOT ST_IsEmpty(geometry))")
    op.create_check_constraint("geometry_revision_positive", "sites", "geometry_revision >= 1")
    op.create_check_constraint("archived_not_active", "sites", "NOT (is_archived AND is_active)")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_sites_archived_not_active"), "sites", type_="check")
    op.drop_constraint(op.f("ck_sites_geometry_revision_positive"), "sites", type_="check")
    op.execute("ALTER TABLE sites DROP CONSTRAINT ck_sites_geometry_valid")
    op.execute("DROP INDEX IF EXISTS uq_sites_one_active_per_project")
    op.execute("DROP INDEX IF EXISTS ix_sites_geometry_gist")
    op.drop_index(op.f("ix_sites_project_id"), table_name="sites")
    op.drop_table("sites")
