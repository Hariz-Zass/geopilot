from pathlib import Path
path=Path("/app/app/services/pdf_ingestion.py")
text=path.read_text(encoding="utf-8")
if "def ingest_acquired_pdf(" in text:
    print("ALREADY_PATCHED"); raise SystemExit(0)
needle="\ndef list_document_pages(\n"
if needle not in text: raise SystemExit("ANCHOR_NOT_FOUND")
src=text[text.index("def ingest_registered_pdf("):text.index(needle)]
new=src.replace("def ingest_registered_pdf(", "def ingest_acquired_pdf(", 1)
new=new.replace('version.source_kind != "upload"', 'version.source_kind != "acquired"', 1)
new=new.replace("manual PDF upload is only valid for upload source versions", "acquired PDF ingestion is only valid for acquired source versions", 1)
new=new.replace('"ingestion_method": "manual_pdf_upload_v1"', '"ingestion_method": "controlled_acquired_pdf_v1"', 1)
new=new.replace("uploaded file does not have a PDF signature", "acquired file does not have a PDF signature", 1)
new=new.replace("uploaded content type is not PDF", "acquired content type is not PDF", 1)
new=new.replace("uploaded bytes do not match immutable version checksum", "acquired bytes do not match immutable version checksum", 1)
new=new.replace("uploaded byte size does not match immutable version metadata", "acquired byte size does not match immutable version metadata", 1)
path.write_text(text.replace(needle, "\n"+new+needle, 1), encoding="utf-8")
print("PATCHED:",path)
