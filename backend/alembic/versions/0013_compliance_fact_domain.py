"""compliance fact domain

Revision ID: 0013
Revises: 0012
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compliance_facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.String(length=160), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("value_type", sa.String(length=24), nullable=False),
        sa.Column("unit", sa.String(length=80), nullable=True),
        sa.Column("numeric_value", sa.Numeric(24, 8), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("boolean_value", sa.Boolean(), nullable=True),
        sa.Column("set_value", sa.JSON(), nullable=True),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_method", sa.String(length=80), nullable=False),
        sa.Column("source_description", sa.Text(), nullable=False),
        sa.Column("source_details", sa.JSON(), nullable=False),
        sa.Column("site_geometry_hash", sa.String(length=64), nullable=False),
        sa.Column("site_geometry_revision", sa.Integer(), nullable=False),
        sa.Column("source_gis_layer_id", sa.Uuid(), nullable=True),
        sa.Column("source_gis_feature_id", sa.Uuid(), nullable=True),
        sa.Column("source_feature_geometry_hash", sa.String(length=64), nullable=True),
        sa.Column("provenance_hash", sa.String(length=64), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_compliance_facts_project_id_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], name=op.f("fk_compliance_facts_site_id_sites"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_compliance_facts_created_by_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_gis_layer_id"], ["gis_layers.id"], name=op.f("fk_compliance_facts_source_gis_layer_id_gis_layers"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_gis_feature_id"], ["gis_features.id"], name=op.f("fk_compliance_facts_source_gis_feature_id_gis_features"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_compliance_facts")),
        sa.UniqueConstraint("provenance_hash", name="uq_compliance_facts_provenance_hash"),
    )
    for col in ("project_id", "site_id", "created_by_user_id", "metric_key", "source_gis_layer_id", "source_gis_feature_id"):
        op.create_index(op.f(f"ix_compliance_facts_{col}"), "compliance_facts", [col], unique=False)
    op.create_check_constraint("compliance_fact_value_type_valid", "compliance_facts", "value_type IN ('numeric','text','boolean','set')")
    op.create_check_constraint("compliance_fact_source_kind_valid", "compliance_facts", "source_kind IN ('user_supplied','gis_analysis')")
    op.create_check_constraint("compliance_fact_payload_shape_valid", "compliance_facts", "(value_type = 'numeric' AND numeric_value IS NOT NULL AND text_value IS NULL AND boolean_value IS NULL AND set_value IS NULL) OR (value_type = 'text' AND numeric_value IS NULL AND text_value IS NOT NULL AND boolean_value IS NULL AND set_value IS NULL) OR (value_type = 'boolean' AND numeric_value IS NULL AND text_value IS NULL AND boolean_value IS NOT NULL AND set_value IS NULL) OR (value_type = 'set' AND numeric_value IS NULL AND text_value IS NULL AND boolean_value IS NULL AND set_value IS NOT NULL)")
    op.create_check_constraint("compliance_fact_source_method_valid", "compliance_facts", "(source_kind = 'user_supplied' AND source_method = 'owner_assertion_v1') OR (source_kind = 'gis_analysis' AND source_method = 'postgis-geography-v1')")
    op.create_check_constraint("compliance_fact_feature_lineage_complete", "compliance_facts", "(source_gis_feature_id IS NULL AND source_gis_layer_id IS NULL AND source_feature_geometry_hash IS NULL) OR (source_gis_feature_id IS NOT NULL AND source_gis_layer_id IS NOT NULL AND source_feature_geometry_hash IS NOT NULL)")


def downgrade() -> None:
    for name in (
        "compliance_fact_feature_lineage_complete",
        "compliance_fact_source_method_valid",
        "compliance_fact_payload_shape_valid",
        "compliance_fact_source_kind_valid",
        "compliance_fact_value_type_valid",
    ):
        op.drop_constraint(op.f(f"ck_compliance_facts_{name}"), "compliance_facts", type_="check")
    for col in reversed(("project_id", "site_id", "created_by_user_id", "metric_key", "source_gis_layer_id", "source_gis_feature_id")):
        op.drop_index(op.f(f"ix_compliance_facts_{col}"), table_name="compliance_facts")
    op.drop_table("compliance_facts")
