from __future__ import annotations

import importlib.util
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REVISION_PATH = BACKEND_ROOT / "alembic" / "versions" / "0002_user_auth.py"


def _load_revision():
    spec = importlib.util.spec_from_file_location("migration_0002", REVISION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_user_revision_follows_database_foundation() -> None:
    migration = _load_revision()
    assert migration.revision == "0002"
    assert migration.down_revision == "0001"


def test_user_revision_creates_only_auth_table(monkeypatch) -> None:
    migration = _load_revision()
    created_tables: list[str] = []
    created_indexes: list[str] = []

    def create_table(name, *args, **kwargs):
        created_tables.append(name)

    def create_index(name, table_name, *args, **kwargs):
        created_indexes.append(f"{table_name}:{name}")

    monkeypatch.setattr(migration.op, "create_table", create_table)
    monkeypatch.setattr(migration.op, "create_index", create_index)
    monkeypatch.setattr(migration.op, "f", lambda value: value)
    migration.upgrade()
    assert created_tables == ["users"]
    assert len(created_indexes) == 1
    assert created_indexes[0].startswith("users:")
