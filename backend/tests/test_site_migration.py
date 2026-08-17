from __future__ import annotations

from pathlib import Path
import re
import subprocess
import os

BACKEND = Path(__file__).resolve().parents[1]


def _alembic(*args: str) -> str:
    env = os.environ.copy()
    env.setdefault("DATABASE_URL", "postgresql+psycopg://geopilot:geopilot@localhost:5432/geopilot")
    return subprocess.run(["alembic", *args], cwd=BACKEND, env=env, check=True, text=True, capture_output=True).stdout


def test_site_migration_0004_remains_in_history() -> None:
    history = _alembic("history")
    assert "0003 -> 0004" in history


def test_offline_upgrade_contains_native_postgis_site_contract() -> None:
    sql = _alembic("upgrade", "head", "--sql")
    assert "CREATE TABLE sites" in sql
    assert re.search(r"geometry\s+geometry\(MULTIPOLYGON,4326\)\s+NOT NULL", sql, re.IGNORECASE)
    assert "CREATE INDEX ix_sites_geometry_gist ON sites USING GIST (geometry)" in sql
    assert "CREATE UNIQUE INDEX uq_sites_one_active_per_project" in sql
    assert "ST_IsValid(geometry)" in sql
    assert "geometry_revision >= 1" in sql
    assert "NOT (is_archived AND is_active)" in sql
    assert "ON DELETE CASCADE" in sql


def test_offline_downgrade_0004_to_0003_removes_site_schema_only() -> None:
    sql = _alembic("downgrade", "0004:0003", "--sql")
    assert "DROP TABLE sites" in sql
    assert "DROP TABLE projects" not in sql
    assert "DROP TABLE users" not in sql
