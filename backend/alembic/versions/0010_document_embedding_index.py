"""pgvector document embedding index provenance

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.types import VectorType

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_embedding_indexes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_revision", sa.String(length=255), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], name=op.f("fk_document_embedding_indexes_document_version_id_document_versions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_embedding_indexes")),
        sa.UniqueConstraint("document_version_id", "provider", "model_name", "model_revision", name="uq_document_embedding_indexes_version_provider_model_revision"),
    )
    op.create_index(op.f("ix_document_embedding_indexes_document_version_id"), "document_embedding_indexes", ["document_version_id"], unique=False)
    op.create_check_constraint("embedding_index_dimensions_valid", "document_embedding_indexes", "dimensions BETWEEN 1 AND 4096")
    op.create_check_constraint("embedding_index_state_valid", "document_embedding_indexes", "state IN ('building','ready','failed')")
    op.create_check_constraint("embedding_index_chunk_count_valid", "document_embedding_indexes", "chunk_count >= 0")

    op.create_table(
        "document_chunk_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("embedding_index_id", sa.Uuid(), nullable=False),
        sa.Column("document_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", VectorType(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["embedding_index_id"], ["document_embedding_indexes.id"], name=op.f("fk_document_chunk_embeddings_embedding_index_id_document_embedding_indexes"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_chunk_id"], ["document_chunks.id"], name=op.f("fk_document_chunk_embeddings_document_chunk_id_document_chunks"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunk_embeddings")),
        sa.UniqueConstraint("embedding_index_id", "document_chunk_id", name="uq_document_chunk_embeddings_index_chunk"),
    )
    op.create_index(op.f("ix_document_chunk_embeddings_embedding_index_id"), "document_chunk_embeddings", ["embedding_index_id"], unique=False)
    op.create_index(op.f("ix_document_chunk_embeddings_document_chunk_id"), "document_chunk_embeddings", ["document_chunk_id"], unique=False)
    op.create_check_constraint("chunk_embedding_dimensions_valid", "document_chunk_embeddings", "dimensions BETWEEN 1 AND 4096")
    op.create_check_constraint("chunk_embedding_checksum_shape", "document_chunk_embeddings", "text_sha256 ~ '^[0-9a-f]{64}$'")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_document_chunk_embeddings_chunk_embedding_checksum_shape"), "document_chunk_embeddings", type_="check")
    op.drop_constraint(op.f("ck_document_chunk_embeddings_chunk_embedding_dimensions_valid"), "document_chunk_embeddings", type_="check")
    op.drop_index(op.f("ix_document_chunk_embeddings_document_chunk_id"), table_name="document_chunk_embeddings")
    op.drop_index(op.f("ix_document_chunk_embeddings_embedding_index_id"), table_name="document_chunk_embeddings")
    op.drop_table("document_chunk_embeddings")
    op.drop_constraint(op.f("ck_document_embedding_indexes_embedding_index_chunk_count_valid"), "document_embedding_indexes", type_="check")
    op.drop_constraint(op.f("ck_document_embedding_indexes_embedding_index_state_valid"), "document_embedding_indexes", type_="check")
    op.drop_constraint(op.f("ck_document_embedding_indexes_embedding_index_dimensions_valid"), "document_embedding_indexes", type_="check")
    op.drop_index(op.f("ix_document_embedding_indexes_document_version_id"), table_name="document_embedding_indexes")
    op.drop_table("document_embedding_indexes")
