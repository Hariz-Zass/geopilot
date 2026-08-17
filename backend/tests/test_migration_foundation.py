from __future__ import annotations

import importlib.util
from pathlib import Path

from app.db.base import Base, NAMING_CONVENTION

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REVISION_PATH = BACKEND_ROOT / "alembic" / "versions" / "0001_database_foundation.py"


def _load_revision():
    spec = importlib.util.spec_from_file_location("migration_0001", REVISION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_database_foundation_does_not_require_domain_metadata() -> None:
    # Later domain tasks may register tables; revision 0001 remains extension-only.
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_constraint_naming_convention_is_locked() -> None:
    assert NAMING_CONVENTION["pk"] == "pk_%(table_name)s"
    assert NAMING_CONVENTION["fk"].startswith("fk_%(table_name)s")
    assert NAMING_CONVENTION["uq"].startswith("uq_%(table_name)s")


def test_first_revision_is_clean_root() -> None:
    migration = _load_revision()
    assert migration.revision == "0001"
    assert migration.down_revision is None


def test_first_revision_only_bootstraps_required_extensions(monkeypatch) -> None:
    migration = _load_revision()
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.upgrade()
    assert statements == [
        "CREATE EXTENSION IF NOT EXISTS postgis",
        "CREATE EXTENSION IF NOT EXISTS vector",
    ]


def test_downgrade_does_not_drop_shared_extensions(monkeypatch) -> None:
    migration = _load_revision()
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(migration.op, "execute", forbidden)
    migration.downgrade()
    assert called is False
