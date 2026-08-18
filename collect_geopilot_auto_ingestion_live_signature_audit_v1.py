from __future__ import annotations

import inspect
import json
from pathlib import Path

MODULES = [
    "app.api.v1.planning_documents",
    "app.services.planning_documents",
    "app.services.document_extraction",
    "app.services.document_chunking",
    "app.services.document_indexing",
]

NAMES = [
    "ingest",
    "ingest_pdf",
    "ingest_document_pdf",
    "ingest_pdf_document",
    "store",
    "extract",
    "extract_document",
    "list_document_pages",
    "build_document_chunks",
    "build_document_embedding_index",
    "create_planning_document",
    "create_document_version",
]

print("=" * 72)
print("GEOPILOT AUTO-INGESTION LIVE SIGNATURE AUDIT V1")
print("READ ONLY")
print("=" * 72)

for module_name in MODULES:
    print()
    print("###", module_name)
    try:
        module = __import__(module_name, fromlist=["*"])
    except Exception as exc:
        print("IMPORT_ERROR:", type(exc).__name__, str(exc))
        continue

    public = []
    for name, value in inspect.getmembers(module):
        if name.startswith("_"):
            continue
        if inspect.isfunction(value) and getattr(value, "__module__", "") == module_name:
            try:
                sig = str(inspect.signature(value))
            except Exception:
                sig = "(signature unavailable)"
            public.append((name, sig))

    print("FUNCTIONS:")
    for name, sig in public:
        print(" ", name, sig)

    for target in NAMES:
        if hasattr(module, target):
            value = getattr(module, target)
            if inspect.isfunction(value):
                print()
                print("--- SOURCE:", module_name + "." + target, "---")
                try:
                    print(inspect.getsource(value))
                except Exception as exc:
                    print("SOURCE_ERROR:", type(exc).__name__, str(exc))

print()
print("### SCHEMA SIGNATURES")
try:
    import app.schemas.planning_document as schema
    for name in (
        "PlanningDocumentCreateRequest",
        "DocumentVersionCreateRequest",
        "DocumentChunkBuildRequest",
        "DocumentEmbeddingIndexBuildRequest",
    ):
        cls = getattr(schema, name, None)
        if cls is None:
            continue
        print()
        print(name)
        try:
            print(json.dumps(cls.model_json_schema(), indent=2, default=str))
        except Exception as exc:
            print("SCHEMA_ERROR:", type(exc).__name__, str(exc))
except Exception as exc:
    print("SCHEMA_IMPORT_ERROR:", type(exc).__name__, str(exc))

print()
print("### RELEVANT SOURCE FILE HEADS")
for rel in (
    "app/api/v1/planning_documents.py",
    "app/services/document_extraction.py",
    "app/services/document_chunking.py",
    "app/services/document_indexing.py",
):
    path = Path("/app") / rel
    print()
    print("===", rel, "===")
    if not path.exists():
        print("MISSING")
        continue
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for i, line in enumerate(lines[:430], start=1):
        if (
            i <= 80
            or "ingest" in line.casefold()
            or "build_document_chunks" in line
            or "build_document_embedding_index" in line
            or "list_document_pages" in line
        ):
            print(f"{i}: {line}")

print()
print("=" * 72)
print("AUDIT COMPLETE - NO CHANGES MADE")
print("=" * 72)
