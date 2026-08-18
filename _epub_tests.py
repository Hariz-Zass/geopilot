from pathlib import Path
p=Path("/app/tests/test_planning_document_acquisition.py")
s=p.read_text(encoding="utf-8-sig")
if "test_epublisiti_adapter_v1_1" not in s:
    s += r