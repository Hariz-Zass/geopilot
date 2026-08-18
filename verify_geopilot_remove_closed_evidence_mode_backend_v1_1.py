from pathlib import Path
import re

root = Path("/app")
files = [
    root / "app/core/config.py",
    root / "app/services/track_b.py",
    root / "app/services/track_b_acceptance.py",
    root / "app/services/track_b_ai.py",
    root / "app/services/track_b_workflow.py",
]

patterns = [
    r"CLOSED EVIDENCE",
    r"closed-evidence",
    r"closed evidence",
    r"closed Track B evidence boundary",
    r"Organizer-only evidence enforcement",
    r"external acquisition is disabled",
    r"TRACK_B_COMPETITION_MODE",
]

failed = []
for path in files:
    text = path.read_text(encoding="utf-8-sig")
    for pattern in patterns:
        if re.search(pattern, text, flags=re.I):
            failed.append(f"{path}:{pattern}")

config = (root / "app/core/config.py").read_text(encoding="utf-8-sig")
ai = (root / "app/services/track_b_ai.py").read_text(encoding="utf-8-sig")
checks = {
    "competition_setting_removed": "track_b_competition_mode" not in config.casefold(),
    "ai_scope_gate_removed": 'not in {"organizer_supplied_only", "server_owned"}' not in ai,
    "grounding_preserved": "Never invent" in ai,
    "numeric_grounding_preserved": "NUMERIC GROUNDING RULE" in ai,
}
for key, ok in checks.items():
    print(f"{key}={'PASS' if ok else 'FAIL'}")
for item in failed:
    print("REMAINS:", item)
if failed or not all(checks.values()):
    raise SystemExit("VERIFY_FAILED")
print("BACKEND_VERIFY_ALL=PASS")
