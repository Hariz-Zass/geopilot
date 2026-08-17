"""Deterministic page-local document chunking lineage

Revision ID: 0009
Revises: 0008
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("document_page_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_sequence", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("chunker_version", sa.String(length=64), nullable=False),
        sa.Column("max_chars", sa.Integer(), nullable=False),
        sa.Column("overlap_chars", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"],
            name=op.f("fk_document_chunks_document_version_id_document_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_page_id"], ["document_pages.id"],
            name=op.f("fk_document_chunks_document_page_id_document_pages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint("document_page_id", "chunk_index", name="uq_document_chunks_page_index"),
        sa.UniqueConstraint("document_version_id", "chunk_sequence", name="uq_document_chunks_version_sequence"),
    )
    op.create_index(op.f("ix_document_chunks_document_version_id"), "document_chunks", ["document_version_id"], unique=False)
    op.create_index(op.f("ix_document_chunks_document_page_id"), "document_chunks", ["document_page_id"], unique=False)
    op.create_check_constraint("page_number_positive", "document_chunks", "page_number >= 1")
    op.create_check_constraint("chunk_index_nonnegative", "document_chunks", "chunk_index >= 0")
    op.create_check_constraint("chunk_sequence_nonnegative", "document_chunks", "chunk_sequence >= 0")
    op.create_check_constraint("chunk_offsets_valid", "document_chunks", "start_char >= 0 AND end_char > start_char")
    op.create_check_constraint("chunk_text_nonempty", "document_chunks", "length(text) > 0")
    op.create_check_constraint("chunk_text_checksum_shape", "document_chunks", "text_sha256 ~ '^[0-9a-f]{64}$'")
    op.create_check_constraint("chunk_max_chars_valid", "document_chunks", "max_chars BETWEEN 256 AND 8000")
    op.create_check_constraint("chunk_overlap_valid", "document_chunks", "overlap_chars >= 0 AND overlap_chars < max_chars AND overlap_chars * 2 <= max_chars")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_document_chunks_chunk_overlap_valid"), "document_chunks", type_="check")
    op.drop_constraint(op.f("ck_document_chunks_chunk_max_chars_valid"), "document_chunks", type_="check")
    op.drop_constraint(op.f("ck_document_chunks_chunk_text_checksum_shape"), "document_chunks", type_="check")
    op.drop_constraint(op.f("ck_document_chunks_chunk_text_nonempty"), "document_chunks", type_="check")
    op.drop_constraint(op.f("ck_document_chunks_chunk_offsets_valid"), "document_chunks", type_="check")
    op.drop_constraint(op.f("ck_document_chunks_chunk_sequence_nonnegative"), "document_chunks", type_="check")
    op.drop_constraint(op.f("ck_document_chunks_chunk_index_nonnegative"), "document_chunks", type_="check")
    op.drop_constraint(op.f("ck_document_chunks_page_number_positive"), "document_chunks", type_="check")
    op.drop_index(op.f("ix_document_chunks_document_page_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_document_version_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
