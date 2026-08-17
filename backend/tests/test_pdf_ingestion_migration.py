from __future__ import annotations

from pathlib import Path


def test_0008_migration_declares_page_lineage_and_no_chunks():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0008_pdf_ingestion.py"
    text = path.read_text()
    assert 'revision: str = "0008"' in text
    assert 'down_revision: Union[str, None] = "0007"' in text
    assert '"document_pages"' in text
    assert '"document_version_id"' in text
    assert 'uq_document_pages_version_page' in text
    assert 'requires_ocr' in text
    assert 'document_chunks' not in text
