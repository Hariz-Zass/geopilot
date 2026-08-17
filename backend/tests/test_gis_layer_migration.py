from pathlib import Path
import os, subprocess
BACKEND=Path(__file__).resolve().parents[1]
def alembic(*args):
    env=os.environ.copy(); env.setdefault('DATABASE_URL','postgresql+psycopg://geopilot:geopilot@localhost:5432/geopilot')
    return subprocess.run(['alembic',*args],cwd=BACKEND,env=env,check=True,text=True,capture_output=True).stdout

def test_0005_remains_in_migration_chain():
    assert '0005' in alembic('history')
def test_upgrade_contains_gis_layer_contract():
    sql=alembic('upgrade','head','--sql')
    for token in ['CREATE TABLE gis_layers','source_checksum_sha256','source_crs','provenance JSON','ON DELETE CASCADE','source_kind IN','is_archived AND is_active']:
        assert token in sql

def test_downgrade_0005_to_0004_only_removes_layers():
    sql=alembic('downgrade','0005:0004','--sql'); assert 'DROP TABLE gis_layers' in sql; assert 'DROP TABLE sites' not in sql
