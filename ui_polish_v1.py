from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "frontend" / "src" / "pages" / "TrackBWorkspacePage.tsx"
BACKUP = ROOT / "artifacts" / "TrackBWorkspacePage.pre_ui_polish_v1.tsx"

BACKUP.parent.mkdir(parents=True, exist_ok=True)

if not TARGET.exists():
    print("ERROR: target not found:", TARGET)
    sys.exit(1)

original = TARGET.read_text(encoding="utf-8")
shutil.copy2(TARGET, BACKUP)

text = original

replacements = {
    "â¬”•": "—",
    "Â·": "·",
    "â ’†": "→",
    "â ’‼/span>": "→</span>",
    "â¬₦": "…",
    "â¬₢": "•",
    "âSĜ•": "✓",
    "Ã•": "✕",
    "Ã⁻d.height}": "×{d.height}",
}

for bad, good in replacements.items():
    text = text.replace(bad, good)

# Judge-facing terminology only.
text = text.replace(
    "GeoPilot Planning Copilot",
    "GeoPilot AI Planning Officer",
)

text = text.replace(
    "measurement first · grounded planning intelligence",
    "measured evidence · grounded planning intelligence",
)

TARGET.write_text(text, encoding="utf-8", newline="\n")

print("============================================================")
print("GEOPILOT UI POLISH V1")
print("============================================================")
print("target =", TARGET)
print("backup =", BACKUP)
print("changed =", text != original)
print("remaining_â =", text.count("â"))
print("remaining_Â =", text.count("Â"))
print("remaining_Ã =", text.count("Ã"))
print("UI_POLISH_V1_PATCH = COMPLETE")
print("BACKEND_CHANGES = NONE")
print("DATABASE_WRITES = NONE")
print("============================================================")