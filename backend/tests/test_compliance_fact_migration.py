from pathlib import Path
import subprocess
import sys


BACKEND = Path(__file__).resolve().parents[1]


def run_alembic(*args):
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=BACKEND,
        text=True,
        capture_output=True,
        check=True,
    )


def test_compliance_fact_migration_is_single_head():
    result = run_alembic("heads")
    assert result.stdout.count("(head)") == 1
    history = run_alembic("history")
    assert "0013" in history.stdout


def test_compliance_fact_upgrade_sql_contains_provenance_and_constraints():
    result = run_alembic("upgrade", "0012:0013", "--sql")
    sql = result.stdout
    assert "CREATE TABLE compliance_facts" in sql
    assert "provenance_hash" in sql
    assert "site_geometry_hash" in sql
    assert "source_gis_feature_id" in sql
    assert "compliance_fact_payload_shape_valid" in sql
    assert "compliance_fact_feature_lineage_complete" in sql


def test_compliance_fact_downgrade_sql_drops_only_new_domain_table():
    result = run_alembic("downgrade", "0013:0012", "--sql")
    sql = result.stdout
    assert "DROP TABLE compliance_facts" in sql
    assert "DROP TABLE policy_criteria" not in sql
