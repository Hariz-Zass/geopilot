from pathlib import Path
path=Path("/app/app/services/planning_document_acquisition.py")
text=path.read_text(encoding="utf-8")
if "ingest_acquired_pdf" not in text:
    old="from app.services.pdf_ingestion import ingest_registered_pdf"
    if old not in text: raise SystemExit("IMPORT_ANCHOR_NOT_FOUND")
    text=text.replace(old, old+", ingest_acquired_pdf", 1)
marker="def ingest_acquired_document("
pos=text.find(marker)
if pos<0: raise SystemExit("AUTO_INGEST_FUNCTION_NOT_FOUND")
idx=text.find("ingest_registered_pdf(", pos)
if idx<0: raise SystemExit("AUTO_INGEST_CALL_NOT_FOUND")
text=text[:idx]+"ingest_acquired_pdf("+text[idx+len("ingest_registered_pdf("):]
path.write_text(text,encoding="utf-8")
print("WIRED:",path)
