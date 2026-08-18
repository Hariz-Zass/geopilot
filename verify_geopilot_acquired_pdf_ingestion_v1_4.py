import inspect
from pathlib import Path

from app.services.pdf_ingestion import ingest_registered_pdf, ingest_acquired_pdf
from app.services.planning_document_acquisition import ingest_acquired_document

manual = inspect.getsource(ingest_registered_pdf)
acquired = inspect.getsource(ingest_acquired_pdf)
pipeline = inspect.getsource(ingest_acquired_document)

checks = {
    "manual_upload_guard": 'version.source_kind != "upload"' in manual,
    "manual_upload_message": "manual PDF upload is only valid for upload source versions" in manual,
    "acquired_source_guard": 'version.source_kind != "acquired"' in acquired,
    "acquired_ingestion_method": '"ingestion_method": "controlled_acquired_pdf_v1"' in acquired,
    "acquired_reuses_extract_pages": "_extract_pages(data)" in acquired,
    "acquired_reuses_storage_target": "_storage_target(" in acquired,
    "acquired_checksum_verification": "hashlib.sha256(data).hexdigest()" in acquired,
    "pipeline_calls_acquired_path": "ingest_acquired_pdf(" in pipeline,
    "pipeline_no_longer_calls_manual_path": "ingest_registered_pdf(" not in pipeline,
}

for key, value in checks.items():
    print(f"{key}={'PASS' if value else 'FAIL'}")

failed = [key for key, value in checks.items() if not value]
if failed:
    raise SystemExit("VERIFY_FAILED: " + ", ".join(failed))

print("VERIFY_ALL=PASS")
