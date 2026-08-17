import inspect
import app.services.pdf_ingestion as mod
def test_acquired_entrypoint_exists():
    assert callable(mod.ingest_acquired_pdf)
def test_manual_guard_preserved():
    s=inspect.getsource(mod.ingest_registered_pdf)
    assert 'version.source_kind != "upload"' in s
    assert "manual PDF upload is only valid for upload source versions" in s
def test_acquired_guard_separate():
    s=inspect.getsource(mod.ingest_acquired_pdf)
    assert 'version.source_kind != "acquired"' in s
    assert "controlled_acquired_pdf_v1" in s
    assert "_extract_pages(data)" in s
    assert "_storage_target(" in s
