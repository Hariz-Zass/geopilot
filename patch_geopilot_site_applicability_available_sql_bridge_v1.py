from pathlib import Path

p = Path("/app/app/services/site_applicability.py")
t = p.read_text(encoding="utf-8-sig")

old_sql = '''              AND s.is_active IS TRUE
              AND s.is_archived IS FALSE
'''
new_sql = '''              AND (
                  :require_active IS FALSE
                  OR s.is_active IS TRUE
              )
              AND s.is_archived IS FALSE
'''
if t.count(old_sql) != 1:
    raise SystemExit(f"ACTIVE_SQL_GATE_COUNT_{t.count(old_sql)}")
t = t.replace(old_sql, new_sql, 1)

old_params = '''                "site_id": str(site_id),
                "project_id": str(project_id),
                "layer_ids": layer_ids,
'''
new_params = '''                "site_id": str(site_id),
                "project_id": str(project_id),
                "layer_ids": layer_ids,
                "require_active": site_state is SiteState.ACTIVE,
'''
if t.count(old_params) != 1:
    raise SystemExit(f"SQL_PARAM_BLOCK_COUNT_{t.count(old_params)}")
t = t.replace(old_params, new_params, 1)

p.write_text(t, encoding="utf-8")
print("PATCHED app/services/site_applicability.py")
