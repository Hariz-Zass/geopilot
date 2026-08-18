from pathlib import Path

target = Path("/app/app/services/site_applicability.py")
text = target.read_text(encoding="utf-8-sig")

old_sql = """              AND s.is_active IS TRUE
              AND s.is_archived IS FALSE
"""
new_sql = """              AND (
                    CAST(:require_active AS boolean) IS FALSE
                    OR s.is_active IS TRUE
              )
              AND s.is_archived IS FALSE
"""

old_params = """                "site_id": str(site_id),
                "project_id": str(project_id),
                "layer_ids": layer_ids,
"""
new_params = """                "site_id": str(site_id),
                "project_id": str(project_id),
                "layer_ids": layer_ids,
                "require_active": site_state is SiteState.ACTIVE,
"""

if "CAST(:require_active AS boolean) IS FALSE" in text:
    raise SystemExit("SQL_LIFECYCLE_BRIDGE_ALREADY_PRESENT")

if text.count(old_sql) != 1:
    raise SystemExit(f"ACTIVE_SQL_GATE_COUNT_{text.count(old_sql)}")

if text.count(old_params) != 1:
    raise SystemExit(f"SQL_PARAM_BLOCK_COUNT_{text.count(old_params)}")

text = text.replace(old_sql, new_sql, 1)
text = text.replace(old_params, new_params, 1)
target.write_text(text, encoding="utf-8")

print("PATCHED app/services/site_applicability.py")
