from pathlib import Path
import os, subprocess
BACKEND=Path(__file__).resolve().parents[1]
def alembic(*args):
    env=os.environ.copy(); env.setdefault('DATABASE_URL','postgresql+psycopg://geopilot:geopilot@localhost:5432/geopilot')
    return subprocess.run(['alembic',*args],cwd=BACKEND,env=env,check=True,text=True,capture_output=True).stdout

def test_0006_remains_in_migration_chain(): assert '0006' in alembic('history')
def test_upgrade_contains_native_gis_feature_contract():
    sql=alembic('upgrade','head','--sql')
    for token in ['CREATE TABLE gis_features','geometry(Geometry,4326)','source_feature_id','geometry_hash','properties JSON','ON DELETE CASCADE','USING gist','ST_SRID(geometry) = 4326','ST_IsValid(geometry)']:
        assert token in sql

def test_downgrade_0006_to_0005_only_removes_features():
    sql=alembic('downgrade','0006:0005','--sql'); assert 'DROP TABLE gis_features' in sql; assert 'DROP TABLE gis_layers' not in sql
