"""project-owned GIS layer metadata domain

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gis_layers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("source_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_crs", sa.String(length=64), nullable=False),
        sa.Column("geometry_type", sa.String(length=32), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_gis_layers_project_id_projects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gis_layers")),
    )
    op.create_index(op.f("ix_gis_layers_project_id"), "gis_layers", ["project_id"], unique=False)
    op.create_check_constraint("archived_not_active", "gis_layers", "NOT (is_archived AND is_active)")
    op.create_check_constraint("source_kind_allowed", "gis_layers", "source_kind IN ('upload','acquired','generated','external_reference')")
    op.create_check_constraint("checksum_sha256_shape", "gis_layers", "source_checksum_sha256 IS NULL OR source_checksum_sha256 ~ '^[0-9a-f]{64}$'")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_gis_layers_checksum_sha256_shape"), "gis_layers", type_="check")
    op.drop_constraint(op.f("ck_gis_layers_source_kind_allowed"), "gis_layers", type_="check")
    op.drop_constraint(op.f("ck_gis_layers_archived_not_active"), "gis_layers", type_="check")
    op.drop_index(op.f("ix_gis_layers_project_id"), table_name="gis_layers")
    op.drop_table("gis_layers")
