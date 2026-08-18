from pathlib import Path
import re

ROOT = Path("/app")
targets = {
    "config": ROOT / "app/core/config.py",
    "track_b": ROOT / "app/services/track_b.py",
    "acceptance": ROOT / "app/services/track_b_acceptance.py",
    "ai": ROOT / "app/services/track_b_ai.py",
    "workflow": ROOT / "app/services/track_b_workflow.py",
    "frontend": ROOT.parent / "frontend/src/pages/TrackBWorkspacePage.tsx",
}

for name, path in targets.items():
    if not path.exists():
        raise SystemExit(f"MISSING:{name}:{path}")

# ---------------------------------------------------------------------
# config.py — remove the competition-mode setting entirely.
# ---------------------------------------------------------------------
p = targets["config"]
text = p.read_text(encoding="utf-8-sig")
text = re.sub(
    r'(?m)^\s*track_b_competition_mode:\s*bool\s*=\s*Field\([^\n]*alias="TRACK_B_COMPETITION_MODE"[^\n]*\)\s*\n',
    "",
    text,
)
p.write_text(text, encoding="utf-8")
print("PATCHED:", p)

# ---------------------------------------------------------------------
# track_b.py — remove organizer-only upload gate and closed-evidence report copy.
# ---------------------------------------------------------------------
p = targets["track_b"]
text = p.read_text(encoding="utf-8-sig")

text = re.sub(
    r'\ndef _assert_competition_upload\(source_kind: str = "upload"\) -> None:\n'
    r'(?:    .*\n)+?(?=\n(?:def|class) )',
    "\n",
    text,
    count=1,
)

# If function survived due formatting, make it a compatibility no-op, not a gate.
if "def _assert_competition_upload(" in text:
    start = text.index("def _assert_competition_upload(")
    nxt = text.find("\ndef ", start + 1)
    if nxt < 0:
        raise SystemExit("TRACK_B_UPLOAD_GUARD_BLOCK_NOT_BOUNDED")
    text = (
        text[:start]
        + 'def _assert_competition_upload(source_kind: str = "upload") -> None:\n'
          '    """Compatibility no-op: closed evidence mode was removed."""\n'
          '    return None\n\n'
        + text[nxt + 1:]
    )

text = text.replace("Closed-evidence declaration", "Evidence provenance declaration")
text = text.replace(
    "This analysis is configured for PLAN-Ai Hackathon 2026 Track B closed-evidence operation. "
    "Spatial measurements are derived from organizer-supplied raster evidence. "
    "GeoPilot is decision support and does not issue statutory approval or certification.",
    "This analysis uses evidence with recorded provenance. Spatial measurements retain their source lineage, "
    "and planning-document evidence may be incorporated through approved GeoPilot retrieval workflows. "
    "GeoPilot is decision support and does not issue statutory approval or certification.",
)
p.write_text(text, encoding="utf-8")
print("PATCHED:", p)

# ---------------------------------------------------------------------
# track_b_acceptance.py — competition mode is no longer a blocker/check.
# ---------------------------------------------------------------------
p = targets["acceptance"]
text = p.read_text(encoding="utf-8-sig")

# Remove the complete competition-mode check block, bounded by rasterio.Env.
text = re.sub(
    r'\n\s*checks\.append\(\{\s*\n'
    r'\s*"key": "competition_mode",.*?'
    r'\n\s*if not settings\.track_b_competition_mode:\s*\n'
    r'\s*blockers\.append\("Enable TRACK_B_COMPETITION_MODE before competition use\."\)\s*\n',
    "\n",
    text,
    count=1,
    flags=re.S,
)

text = text.replace(
    "Organizer-only before/after pair is locally available, lineage-verified, and analysis-compatible.",
    "Before/after raster pair is locally available, lineage-verified, and analysis-compatible.",
)
text = text.replace(
    "Run the full Track B mission and verify AI outputs against the organizer evidence before presentation.",
    "Run the full Track B mission and verify AI outputs against their cited evidence before presentation.",
)
p.write_text(text, encoding="utf-8")
print("PATCHED:", p)

# ---------------------------------------------------------------------
# track_b_ai.py — remove closed-evidence scope gate and terminology.
# Preserve grounding / numeric validation / professional review limits.
# ---------------------------------------------------------------------
p = targets["ai"]
text = p.read_text(encoding="utf-8-sig")

# Remove all guards that reject evidence solely because scope is not organizer/server-only.
text = re.sub(
    r'\n\s*if not evidence or any\(e\.get\("scope"\) not in \{"organizer_supplied_only", "server_owned"\} for e in evidence\):\s*\n'
    r'\s*raise TrackBAIError\("[^"]*closed Track B evidence boundary\."\)\s*',
    "\n    if not evidence:\n        raise TrackBAIError(\"Track B analysis has no evidence payload.\")\n",
    text,
)

text = text.replace("closed-evidence planning decision packet", "grounded planning decision packet")
text = text.replace("CLOSED-EVIDENCE TRACK B FACTS:", "GROUNDED TRACK B FACTS:")
text = text.replace("CLOSED-EVIDENCE URBAN/RURAL FACTS:", "GROUNDED URBAN/RURAL FACTS:")
text = text.replace("CLOSED-EVIDENCE TRACK B DECISION FACTS:", "GROUNDED TRACK B DECISION FACTS:")
text = text.replace(
    "Convert ONLY the supplied organizer-derived deterministic evidence into an auditable planner decision brief.",
    "Convert the supplied grounded evidence into an auditable planner decision brief. "
    "Use only evidence present in the request context; do not invent unsupported facts.",
)
text = text.replace(
    "Compare ONLY the supplied organizer-derived urban and rural temporal evidence.",
    "Compare the supplied grounded urban and rural temporal evidence.",
)
text = text.replace(
    "Interpret ONLY the supplied deterministic facts.",
    "Interpret the supplied grounded facts only.",
)

p.write_text(text, encoding="utf-8")
print("PATCHED:", p)

# ---------------------------------------------------------------------
# track_b_workflow.py — remove organizer-only wording.
# ---------------------------------------------------------------------
p = targets["workflow"]
text = p.read_text(encoding="utf-8-sig")
text = text.replace(
    "Grounded AI output generated inside the organizer-only evidence boundary.",
    "Grounded AI output generated from evidence with recorded provenance.",
)
p.write_text(text, encoding="utf-8")
print("PATCHED:", p)

# ---------------------------------------------------------------------
# Frontend — remove visible mode, organizer-only tags and closed-mode wording.
# ---------------------------------------------------------------------
p = targets["frontend"]
text = p.read_text(encoding="utf-8-sig")

text = text.replace("// temporal question -> Track B closed-evidence decision flow",
                    "// temporal question -> Track B grounded decision flow")

# Remove the badge entirely rather than rename it.
text = re.sub(
    r'<div className="evidence-lock"><span className="pulse-dot"\s*/>\s*CLOSED EVIDENCE MODE<br\s*/><small>Organizer data only · external acquisition disabled</small></div>',
    "",
    text,
    count=1,
)

text = text.replace("<code>ORGANIZER_ONLY</code>", "<code>GROUNDED_EVIDENCE</code>")
text = text.replace(
    "Register matching organizer-only Urban and Rural T1/T2 pairs with the same Site and data stage.",
    "Register matching Urban and Rural T1/T2 pairs with the same Site and data stage.",
)
text = text.replace(
    "GeoPilot automatically selects organizer-only before/after pairs for both challenge contexts, runs deterministic temporal analysis, grounded AI interpretation, planner decision briefs, and strategic comparison.",
    "GeoPilot automatically selects available before/after pairs for both challenge contexts, runs deterministic temporal analysis, grounded AI interpretation, planner decision briefs, and strategic comparison.",
)

p.write_text(text, encoding="utf-8")
print("PATCHED:", p)

print("CLOSED_EVIDENCE_MODE_REMOVAL_PATCH=PASS")
