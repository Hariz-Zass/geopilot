from pathlib import Path

path = Path("/app/tests/test_planning_document_acquisition.py")
text = path.read_text(encoding="utf-8")

start_marker = "def test_auto_ingestion_v1_1_pipeline_calls_existing_layers("
start = text.find(start_marker)
if start < 0:
    raise SystemExit("TARGET_TEST_NOT_FOUND")

next_def = text.find("\ndef ", start + len(start_marker))
end = len(text) if next_def < 0 else next_def
block = text[start:end]

if 'mod, "ingest_acquired_pdf",' in block:
    print("TARGET_TEST_ALREADY_REPAIRED")
    raise SystemExit(0)

if 'mod, "ingest_registered_pdf",' not in block:
    print("TARGET_TEST_BLOCK_BEGIN")
    print(block)
    print("TARGET_TEST_BLOCK_END")
    raise SystemExit("STALE_MOCK_REFERENCE_NOT_FOUND_IN_TARGET_TEST")

new_block = block.replace(
    'mod, "ingest_registered_pdf",',
    'mod, "ingest_acquired_pdf",',
    1,
)

path.write_text(text[:start] + new_block + text[end:], encoding="utf-8")
print("PATCHED:", path)
print("replacement=ingest_registered_pdf->ingest_acquired_pdf")
