from pathlib import Path
import os
import subprocess

BACKEND = Path(__file__).resolve().parents[1]


def alembic(*args: str) -> str:
    env = os.environ.copy()
    env.setdefault("DATABASE_URL", "postgresql+psycopg://geopilot:geopilot@localhost:5432/geopilot")
    return subprocess.run(
        ["alembic", *args],
        cwd=BACKEND,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def test_0007_remains_in_linear_migration_chain():
    history = alembic("history")
    assert "0006 -> 0007" in history


def test_upgrade_contains_planning_document_and_version_contract():
    sql = alembic("upgrade", "head", "--sql")
    for token in [
        "CREATE TABLE planning_documents",
        "CREATE TABLE document_versions",
        "document_class IN ('RFN','RSN','RT','RKK','GPP'",
        "uq_document_versions_document_sequence",
        "uq_document_versions_document_checksum",
        "checksum_sha256",
        "source_identity_required",
        "ON DELETE CASCADE",
    ]:
        assert token in sql


def test_downgrade_0007_to_0006_only_removes_document_foundation():
    sql = alembic("downgrade", "0007:0006", "--sql")
    assert "DROP TABLE document_versions" in sql
    assert "DROP TABLE planning_documents" in sql
    assert "DROP TABLE gis_features" not in sql
