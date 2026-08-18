from __future__ import annotations
import inspect
import app.services.pdf_ingestion as mod

print("=" * 72)
print("GEOPILOT PDF INGESTION SOURCE AUDIT V1")
print("READ ONLY")
print("=" * 72)

for name in (
    "_storage_root",
    "_target_path",
    "_extract_pdf",
    "_validate_pdf",
    "ingest_registered_pdf",
    "list_document_pages",
):
    value = getattr(mod, name, None)
    if value is None:
        continue
    print()
    print("###", name)
    try:
        print("signature:", inspect.signature(value))
    except Exception:
        pass
    try:
        print(inspect.getsource(value))
    except Exception as exc:
        print("SOURCE_ERROR:", type(exc).__name__, str(exc))

print()
print("PUBLIC FUNCTIONS:")
for name, value in inspect.getmembers(mod, inspect.isfunction):
    if getattr(value, "__module__", "") == mod.__name__:
        try:
            print(name, inspect.signature(value))
        except Exception:
            print(name)

print("=" * 72)
print("AUDIT COMPLETE - NO CHANGES")
print("=" * 72)
