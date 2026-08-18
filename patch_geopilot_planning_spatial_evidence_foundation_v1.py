from pathlib import Path

root = Path("/app")
service_source = root / "_planning_spatial_evidence_service.py"
test_source = root / "_planning_spatial_evidence_test.py"

service_target = root / "app/services/planning_spatial_evidence.py"
test_target = root / "tests/test_planning_spatial_evidence_foundation_v1.py"

if service_target.exists():
    raise SystemExit("SERVICE_ALREADY_EXISTS")

service_target.write_text(
    service_source.read_text(encoding="utf-8-sig"),
    encoding="utf-8",
)
test_target.write_text(
    test_source.read_text(encoding="utf-8-sig"),
    encoding="utf-8",
)

print("CREATED app/services/planning_spatial_evidence.py")
print("CREATED tests/test_planning_spatial_evidence_foundation_v1.py")
