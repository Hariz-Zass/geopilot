"""policy reference workflow

Revision ID: 0011
Revises: 0010
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_references",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("document_page_id", sa.Uuid(), nullable=False),
        sa.Column("document_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("document_class_snapshot", sa.String(length=32), nullable=False),
        sa.Column("authority_snapshot", sa.String(length=255), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("version_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("page_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("chunk_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_wording", sa.Text(), nullable=False),
        sa.Column("policy_statement", sa.Text(), nullable=False),
        sa.Column("representation_state", sa.String(length=24), nullable=False),
        sa.Column("review_state", sa.String(length=24), nullable=False),
        sa.Column("applicability_status", sa.String(length=32), nullable=False),
        sa.Column("applicability_notes", sa.Text(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_policy_references_project_id_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["planning_documents.id"], name=op.f("fk_policy_references_document_id_planning_documents"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], name=op.f("fk_policy_references_document_version_id_document_versions"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_page_id"], ["document_pages.id"], name=op.f("fk_policy_references_document_page_id_document_pages"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_chunk_id"], ["document_chunks.id"], name=op.f("fk_policy_references_document_chunk_id_document_chunks"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_policy_references_created_by_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], name=op.f("fk_policy_references_reviewed_by_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_references")),
    )
    for col in ("project_id", "document_id", "document_version_id", "document_page_id", "document_chunk_id", "created_by_user_id", "reviewed_by_user_id"):
        op.create_index(op.f(f"ix_policy_references_{col}"), "policy_references", [col], unique=False)
    op.create_check_constraint("policy_reference_page_number_valid", "policy_references", "page_number >= 1")
    op.create_check_constraint("policy_reference_version_checksum_shape", "policy_references", "version_checksum_sha256 ~ '^[0-9a-f]{64}$'")
    op.create_check_constraint("policy_reference_page_checksum_shape", "policy_references", "page_text_sha256 ~ '^[0-9a-f]{64}$'")
    op.create_check_constraint("policy_reference_chunk_checksum_shape", "policy_references", "chunk_text_sha256 ~ '^[0-9a-f]{64}$'")
    op.create_check_constraint("policy_reference_representation_state_valid", "policy_references", "representation_state IN ('draft','final')")
    op.create_check_constraint("policy_reference_review_state_valid", "policy_references", "review_state IN ('unreviewed','requires_review','verified','rejected')")
    op.create_check_constraint("policy_reference_applicability_status_valid", "policy_references", "applicability_status IN ('unassessed','requires_review','applicable','not_applicable','limited')")
    op.create_check_constraint("policy_reference_final_review_consistency", "policy_references", "(representation_state = 'draft' AND review_state IN ('unreviewed','requires_review')) OR (representation_state = 'final' AND review_state IN ('verified','rejected'))")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_policy_references_policy_reference_final_review_consistency"), "policy_references", type_="check")
    op.drop_constraint(op.f("ck_policy_references_policy_reference_applicability_status_valid"), "policy_references", type_="check")
    op.drop_constraint(op.f("ck_policy_references_policy_reference_review_state_valid"), "policy_references", type_="check")
    op.drop_constraint(op.f("ck_policy_references_policy_reference_representation_state_valid"), "policy_references", type_="check")
    op.drop_constraint(op.f("ck_policy_references_policy_reference_chunk_checksum_shape"), "policy_references", type_="check")
    op.drop_constraint(op.f("ck_policy_references_policy_reference_page_checksum_shape"), "policy_references", type_="check")
    op.drop_constraint(op.f("ck_policy_references_policy_reference_version_checksum_shape"), "policy_references", type_="check")
    op.drop_constraint(op.f("ck_policy_references_policy_reference_page_number_valid"), "policy_references", type_="check")
    for col in reversed(("project_id", "document_id", "document_version_id", "document_page_id", "document_chunk_id", "created_by_user_id", "reviewed_by_user_id")):
        op.drop_index(op.f(f"ix_policy_references_{col}"), table_name="policy_references")
    op.drop_table("policy_references")
