from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import ForeignKeyConstraint

from app import models  # noqa: F401
from app.db.base import Base

ROOT = Path(__file__).resolve().parents[1]


def _load_revision(filename: str):
    path = ROOT / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_project_revision_chain_is_0002_to_0003() -> None:
    revision = _load_revision("0003_project_domain.py")
    assert revision.revision == "0003"
    assert revision.down_revision == "0002"


def test_metadata_preserves_users_and_projects() -> None:
    assert {"users", "projects"}.issubset(set(Base.metadata.tables))


def test_project_metadata_has_owner_foreign_key_and_expected_columns() -> None:
    table = Base.metadata.tables["projects"]
    assert set(table.columns.keys()) == {
        "id",
        "owner_id",
        "name",
        "description",
        "is_archived",
        "created_at",
        "updated_at",
    }
    foreign_keys = [c for c in table.constraints if isinstance(c, ForeignKeyConstraint)]
    assert len(foreign_keys) == 1
    fk = foreign_keys[0]
    assert list(fk.columns)[0].name == "owner_id"
    assert list(fk.elements)[0].target_fullname == "users.id"
    assert fk.ondelete == "CASCADE"
