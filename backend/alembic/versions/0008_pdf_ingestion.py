"""PDF ingestion and page-level extraction foundation

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("extraction_method", sa.String(length=32), nullable=False),
        sa.Column("extraction_state", sa.String(length=32), nullable=False),
        sa.Column("requires_ocr", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"],
            name=op.f("fk_document_pages_document_version_id_document_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_pages")),
        sa.UniqueConstraint("document_version_id", "page_number", name="uq_document_pages_version_page"),
    )
    op.create_index(op.f("ix_document_pages_document_version_id"), "document_pages", ["document_version_id"], unique=False)
    op.create_check_constraint("page_number_positive", "document_pages", "page_number >= 1")
    op.create_check_constraint("char_count_nonnegative", "document_pages", "char_count >= 0")
    op.create_check_constraint("text_checksum_shape", "document_pages", "text_sha256 ~ '^[0-9a-f]{64}$'")
    op.create_check_constraint(
        "page_extraction_state_allowed", "document_pages",
        "extraction_state IN ('ready','empty','failed')",
    )
    op.create_check_constraint(
        "page_extraction_method_allowed", "document_pages",
        "extraction_method IN ('pypdf_text','none')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_document_pages_page_extraction_method_allowed"), "document_pages", type_="check")
    op.drop_constraint(op.f("ck_document_pages_page_extraction_state_allowed"), "document_pages", type_="check")
    op.drop_constraint(op.f("ck_document_pages_text_checksum_shape"), "document_pages", type_="check")
    op.drop_constraint(op.f("ck_document_pages_char_count_nonnegative"), "document_pages", type_="check")
    op.drop_constraint(op.f("ck_document_pages_page_number_positive"), "document_pages", type_="check")
    op.drop_index(op.f("ix_document_pages_document_version_id"), table_name="document_pages")
    op.drop_table("document_pages")
