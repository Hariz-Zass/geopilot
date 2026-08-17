from pathlib import Path
from sqlalchemy import create_engine
from app.db.base import Base


def test_embedding_tables_registered_without_hybrid_search_schema():
    engine=create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    assert "document_embedding_indexes" in Base.metadata.tables
    assert "document_chunk_embeddings" in Base.metadata.tables
    assert "document_retrieval_results" not in Base.metadata.tables


def test_0010_migration_uses_native_vector_and_no_ann_index_yet():
    text=Path("alembic/versions/0010_document_embedding_index.py").read_text()
    assert 'Revision ID: 0010' in text and 'Revises: 0009' in text
    assert 'VectorType()' in text
    assert 'document_embedding_indexes' in text and 'document_chunk_embeddings' in text
    assert 'hnsw' not in text.lower() and 'ivfflat' not in text.lower()
