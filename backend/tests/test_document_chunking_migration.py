from __future__ import annotations

from pathlib import Path


def test_0009_migration_declares_chunk_lineage_without_embeddings():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0009_document_chunking.py"
    text = path.read_text()
    assert 'revision: str = "0009"' in text
    assert 'down_revision: Union[str, None] = "0008"' in text
    assert '"document_chunks"' in text
    assert '"document_version_id"' in text
    assert '"document_page_id"' in text
    assert 'uq_document_chunks_page_index' in text
    assert 'uq_document_chunks_version_sequence' in text
    assert 'chunker_version' in text
    assert 'start_char' in text and 'end_char' in text
    assert 'embedding' not in text.lower()
    assert 'vector(' not in text.lower()
