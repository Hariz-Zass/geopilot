"""policy criterion domain

Revision ID: 0012
Revises: 0011
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_criteria",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("policy_reference_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("metric_key", sa.String(length=160), nullable=False),
        sa.Column("value_type", sa.String(length=24), nullable=False),
        sa.Column("operator", sa.String(length=24), nullable=False),
        sa.Column("unit", sa.String(length=80), nullable=True),
        sa.Column("threshold_numeric", sa.Numeric(24, 8), nullable=True),
        sa.Column("lower_numeric", sa.Numeric(24, 8), nullable=True),
        sa.Column("upper_numeric", sa.Numeric(24, 8), nullable=True),
        sa.Column("expected_text", sa.Text(), nullable=True),
        sa.Column("expected_boolean", sa.Boolean(), nullable=True),
        sa.Column("expected_values", sa.JSON(), nullable=True),
        sa.Column("source_evidence_text", sa.Text(), nullable=False),
        sa.Column("interpretation_notes", sa.Text(), nullable=True),
        sa.Column("applicability_notes", sa.Text(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("representation_state", sa.String(length=24), nullable=False),
        sa.Column("review_state", sa.String(length=24), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_policy_criteria_project_id_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_reference_id"], ["policy_references.id"], name=op.f("fk_policy_criteria_policy_reference_id_policy_references"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_policy_criteria_created_by_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], name=op.f("fk_policy_criteria_reviewed_by_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_criteria")),
        sa.UniqueConstraint("project_id", "code", name="uq_policy_criteria_project_code"),
    )
    for col in ("project_id", "policy_reference_id", "created_by_user_id", "reviewed_by_user_id"):
        op.create_index(op.f(f"ix_policy_criteria_{col}"), "policy_criteria", [col], unique=False)
    op.create_check_constraint("policy_criterion_representation_state_valid", "policy_criteria", "representation_state IN ('draft','final')")
    op.create_check_constraint("policy_criterion_review_state_valid", "policy_criteria", "review_state IN ('unreviewed','requires_review','verified','rejected')")
    op.create_check_constraint("policy_criterion_value_type_valid", "policy_criteria", "value_type IN ('numeric','text','boolean','set','manual_review')")
    op.create_check_constraint("policy_criterion_operator_valid", "policy_criteria", "operator IN ('eq','ne','gt','gte','lt','lte','between','in','not_in','bool_eq','manual_review')")
    op.create_check_constraint("policy_criterion_final_review_consistency", "policy_criteria", "(representation_state = 'draft' AND review_state IN ('unreviewed','requires_review')) OR (representation_state = 'final' AND review_state IN ('verified','rejected'))")
    op.create_check_constraint("policy_criterion_type_operator_consistency", "policy_criteria", "(value_type = 'numeric' AND operator IN ('eq','ne','gt','gte','lt','lte','between')) OR (value_type = 'text' AND operator IN ('eq','ne')) OR (value_type = 'set' AND operator IN ('in','not_in')) OR (value_type = 'boolean' AND operator = 'bool_eq') OR (value_type = 'manual_review' AND operator = 'manual_review')")
    op.create_check_constraint("policy_criterion_between_bounds_valid", "policy_criteria", "(operator = 'between' AND lower_numeric IS NOT NULL AND upper_numeric IS NOT NULL AND lower_numeric <= upper_numeric) OR (operator <> 'between')")
    op.create_check_constraint("policy_criterion_payload_shape_valid", "policy_criteria", "(value_type = 'numeric' AND ((operator = 'between' AND threshold_numeric IS NULL AND lower_numeric IS NOT NULL AND upper_numeric IS NOT NULL) OR (operator <> 'between' AND threshold_numeric IS NOT NULL AND lower_numeric IS NULL AND upper_numeric IS NULL))) OR (value_type = 'text' AND expected_text IS NOT NULL) OR (value_type = 'boolean' AND expected_boolean IS NOT NULL) OR (value_type = 'set' AND expected_values IS NOT NULL) OR (value_type = 'manual_review')")


def downgrade() -> None:
    for name in (
        "policy_criterion_payload_shape_valid",
        "policy_criterion_between_bounds_valid",
        "policy_criterion_type_operator_consistency",
        "policy_criterion_final_review_consistency",
        "policy_criterion_operator_valid",
        "policy_criterion_value_type_valid",
        "policy_criterion_review_state_valid",
        "policy_criterion_representation_state_valid",
    ):
        op.drop_constraint(op.f(f"ck_policy_criteria_{name}"), "policy_criteria", type_="check")
    for col in reversed(("project_id", "policy_reference_id", "created_by_user_id", "reviewed_by_user_id")):
        op.drop_index(op.f(f"ix_policy_criteria_{col}"), table_name="policy_criteria")
    op.drop_table("policy_criteria")
