from pathlib import Path

service = Path("/app/app/services/planning_document_acquisition.py")
text = service.read_text(encoding="utf-8-sig")

if "EPUBLISITI_HOME_URL" in text and "_extract_epublisiti" in text and 'if kind in {"RT", "RSN", "RKK"}' in text:
    print("Provider V1.1 markers already present; no re-patch required.")
    raise SystemExit(0)

raise SystemExit("BLOCKED: current provider does not contain the expected V1.1 ePublisiti patch.")
