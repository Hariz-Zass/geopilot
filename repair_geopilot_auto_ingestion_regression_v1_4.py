from pathlib import Path

path = Path("/app/tests/test_planning_document_acquisition.py")
text = path.read_text(encoding="utf-8")

name = "def test_auto_ingestion_v1_1_pipeline_calls_existing_layers("
start = text.find(name)
if start < 0:
    raise SystemExit("TARGET_TEST_NOT_FOUND")

next_def = text.find("\ndef ", start + len(name))
end = len(text) if next_def < 0 else next_def
block = text[start:end]

if 'mod, "ingest_acquired_pdf",' in block:
    print("TARGET_TEST_ALREADY_REPAIRED")
elif 'mod, "ingest_registered_pdf",' in block:
    block = block.replace(
        'mod, "ingest_registered_pdf",',
        'mod, "ingest_acquired_pdf",',
        1,
    )
    text = text[:start] + block + text[end:]
    path.write_text(text, encoding="utf-8")
    print("TARGET_TEST_REPAIRED")
else:
    print("TARGET_TEST_BLOCK_START")
    print(block)
    print("TARGET_TEST_BLOCK_END")
    raise SystemExit("EXPECTED_MOCK_NOT_FOUND")

# Re-read and verify deterministically.
text = path.read_text(encoding="utf-8")
start = text.find(name)
next_def = text.find("\ndef ", start + len(name))
end = len(text) if next_def < 0 else next_def
block = text[start:end]
assert 'mod, "ingest_acquired_pdf",' in block
assert 'mod, "ingest_registered_pdf",' not in block
print("TARGET_TEST_VERIFY=PASS")
