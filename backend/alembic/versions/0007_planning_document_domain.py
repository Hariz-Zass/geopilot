"""project-owned planning document and immutable version lineage foundation

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DOCUMENT_CLASSES = "'RFN','RSN','RT','RKK','GPP','CIRCULAR','TECHNICAL_GUIDELINE','LOCAL_AUTHORITY','OTHER'"
_SOURCE_KINDS = "'upload','acquired','external_reference'"
_INGESTION_STATES = "'registered','available','failed'"
_EXTRACTION_STATES = "'pending','ready','failed','requires_review'"
_INDEX_STATES = "'pending','ready','failed'"
_REVIEW_STATES = "'unreviewed','reviewed','requires_review'"


def upgrade() -> None:
    op.create_table(
        "planning_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("document_class", sa.String(length=32), nullable=False),
        sa.Column("authority", sa.String(length=255), nullable=False),
        sa.Column("jurisdiction", sa.String(length=255), nullable=True),
        sa.Column("geographic_applicability", sa.JSON(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name=op.f("fk_planning_documents_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planning_documents")),
    )
    op.create_index(op.f("ix_planning_documents_project_id"), "planning_documents", ["project_id"], unique=False)
    op.create_check_constraint(
        "document_class_allowed",
        "planning_documents",
        f"document_class IN ({_DOCUMENT_CLASSES})",
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_sequence", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(length=120), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("storage_uri", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("ingestion_state", sa.String(length=32), nullable=False),
        sa.Column("extraction_state", sa.String(length=32), nullable=False),
        sa.Column("index_state", sa.String(length=32), nullable=False),
        sa.Column("review_state", sa.String(length=32), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["planning_documents.id"],
            name=op.f("fk_document_versions_document_id_planning_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_versions")),
        sa.UniqueConstraint("document_id", "version_sequence", name="uq_document_versions_document_sequence"),
        sa.UniqueConstraint("document_id", "checksum_sha256", name="uq_document_versions_document_checksum"),
    )
    op.create_index(op.f("ix_document_versions_document_id"), "document_versions", ["document_id"], unique=False)
    op.create_check_constraint("version_sequence_positive", "document_versions", "version_sequence >= 1")
    op.create_check_constraint("publication_year_range", "document_versions", "publication_year IS NULL OR publication_year BETWEEN 1900 AND 2200")
    op.create_check_constraint("file_size_nonnegative", "document_versions", "file_size_bytes IS NULL OR file_size_bytes >= 0")
    op.create_check_constraint("checksum_shape", "document_versions", "checksum_sha256 ~ '^[0-9a-f]{64}$'")
    op.create_check_constraint("source_kind_allowed", "document_versions", f"source_kind IN ({_SOURCE_KINDS})")
    op.create_check_constraint("ingestion_state_allowed", "document_versions", f"ingestion_state IN ({_INGESTION_STATES})")
    op.create_check_constraint("extraction_state_allowed", "document_versions", f"extraction_state IN ({_EXTRACTION_STATES})")
    op.create_check_constraint("index_state_allowed", "document_versions", f"index_state IN ({_INDEX_STATES})")
    op.create_check_constraint("review_state_allowed", "document_versions", f"review_state IN ({_REVIEW_STATES})")
    op.create_check_constraint(
        "source_identity_required",
        "document_versions",
        "(source_kind = 'upload' AND source_filename IS NOT NULL) OR "
        "(source_kind IN ('acquired','external_reference') AND source_uri IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_document_versions_source_identity_required"), "document_versions", type_="check")
    op.drop_constraint(op.f("ck_document_versions_review_state_allowed"), "document_versions", type_="check")
    op.drop_constraint(op.f("ck_document_versions_index_state_allowed"), "document_versions", type_="check")
    op.drop_constraint(op.f("ck_document_versions_extraction_state_allowed"), "document_versions", type_="check")
    op.drop_constraint(op.f("ck_document_versions_ingestion_state_allowed"), "document_versions", type_="check")
    op.drop_constraint(op.f("ck_document_versions_source_kind_allowed"), "document_versions", type_="check")
    op.drop_constraint(op.f("ck_document_versions_checksum_shape"), "document_versions", type_="check")
    op.drop_constraint(op.f("ck_document_versions_file_size_nonnegative"), "document_versions", type_="check")
    op.drop_constraint(op.f("ck_document_versions_publication_year_range"), "document_versions", type_="check")
    op.drop_constraint(op.f("ck_document_versions_version_sequence_positive"), "document_versions", type_="check")
    op.drop_index(op.f("ix_document_versions_document_id"), table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_constraint(op.f("ck_planning_documents_document_class_allowed"), "planning_documents", type_="check")
    op.drop_index(op.f("ix_planning_documents_project_id"), table_name="planning_documents")
    op.drop_table("planning_documents")
