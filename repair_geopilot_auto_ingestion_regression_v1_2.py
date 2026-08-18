from pathlib import Path

path = Path("/app/tests/test_planning_document_acquisition.py")
text = path.read_text(encoding="utf-8")

old = '''        monkeypatch.setattr(
            mod, "ingest_registered_pdf",
            lambda *a, **k: (calls.append("ingest") or ingestion),
        )
'''
new = '''        monkeypatch.setattr(
            mod, "ingest_acquired_pdf",
            lambda *a, **k: (calls.append("ingest") or ingestion),
        )
'''

if old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("PATCHED:", path)
elif 'mod, "ingest_acquired_pdf",' in text:
    print("ALREADY_PATCHED")
else:
    raise SystemExit("EXPECTED_TEST_BLOCK_NOT_FOUND")
