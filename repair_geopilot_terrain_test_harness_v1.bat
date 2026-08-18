@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo GeoPilot Terrain Test Harness Repair V1
echo Minimal test-only repair + regression verification
echo ============================================================
echo.

if not exist "backend\tests\test_terrain_acquisition.py" (
  echo BLOCKED: terrain test file missing.
  pause
  exit /b 1
)

for /f "tokens=2-4 delims=/ " %%a in ("%date%") do set D=%%c%%a%%b
for /f "tokens=1-3 delims=:., " %%a in ("%time%") do set T=%%a%%b%%c
set T=%T: =0%
set "BACKUP=artifacts\terrain_test_harness_repair_v1_backup_%D%_%T%"
mkdir "%BACKUP%" >nul 2>&1
copy /y "backend\tests\test_terrain_acquisition.py" "%BACKUP%\test_terrain_acquisition.py" >nul
echo BACKUP: %CD%\%BACKUP%

echo.
echo [1] Apply minimal fixture repair to test file only...
docker compose exec -T backend python -c "from pathlib import Path; p=Path('/app/tests/test_terrain_acquisition.py'); s=p.read_text(encoding='utf-8-sig'); marker='from sqlalchemy import select\n'; add='from sqlalchemy import create_engine, event, select\nfrom sqlalchemy.orm import Session, sessionmaker\nfrom sqlalchemy.pool import StaticPool\nimport pytest\n\nfrom app.db.base import Base\nfrom app.models.project import Project\nfrom app.models.site import Site\nfrom app.models.user import User\n\n@pytest.fixture()\ndef terrain_context():\n    engine = create_engine(\"sqlite+pysqlite:///:memory:\", connect_args={\"check_same_thread\": False}, poolclass=StaticPool)\n    @event.listens_for(engine, \"connect\")\n    def spatial_passthrough(dbapi_connection, connection_record):\n        dbapi_connection.create_function(\"ST_GeomFromEWKT\", 1, lambda value: value)\n        dbapi_connection.create_function(\"ST_AsEWKT\", 1, lambda value: value)\n    Base.metadata.create_all(engine)\n    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)\n    with factory() as session:\n        owner = User(email=\"terrain-owner@example.com\", display_name=\"Terrain Owner\", password_hash=\"test-only-password-hash\", is_active=True)\n        session.add(owner); session.flush()\n        project = Project(owner_id=owner.id, name=\"Terrain Project\", description=\"test\")\n        session.add(project); session.flush()\n        site = Site(project_id=project.id, name=\"Terrain Site\", geometry=\"SRID=4326;MULTIPOLYGON(((101.70 3.00,101.71 3.00,101.71 3.01,101.70 3.01,101.70 3.00)))\", geometry_hash=\"0\"*64, geometry_revision=1, is_active=True, is_archived=False)\n        session.add(site); session.commit(); session.refresh(owner); session.refresh(project); session.refresh(site)\n        yield session, owner, project, site\n    Base.metadata.drop_all(engine); engine.dispose()\n\n'; assert marker in s, 'expected import marker missing'; s=s.replace(marker, add, 1); old='def test_manual_dem_precedence(session, owner, project, site):'; new='def test_manual_dem_precedence(terrain_context):\n    session, owner, project, site = terrain_context'; assert old in s, 'manual DEM test signature missing'; s=s.replace(old,new,1); p.write_text(s,encoding='utf-8')"
if errorlevel 1 goto :fail

echo.
echo [2] Syntax check...
docker compose exec -T backend python -m py_compile tests/test_terrain_acquisition.py
if errorlevel 1 goto :fail

echo.
echo [3] Run complete terrain acquisition test file...
docker compose exec -T backend python -m pytest -q tests/test_terrain_acquisition.py
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo TERRAIN TEST HARNESS REPAIR V1 PASS
echo ============================================================
echo Test-only fixture repair: PASS
echo Manual DEM precedence: PASS
echo CDSE mocked OAuth/Process contract: PASS
echo Production terrain service changed: NO
echo DB changed: NO
echo Migration created: NO
echo Frontend changed: NO
echo Live CDSE network acceptance: NOT RUN
echo ============================================================
echo.
pause
exit /b 0

:fail
echo.
echo ============================================================
echo REPAIR / VERIFICATION FAILED
echo ============================================================
echo Backup retained at:
echo %CD%\%BACKUP%
echo Do not run live CDSE acceptance yet.
echo Paste the complete output back into ChatGPT.
echo ============================================================
echo.
pause
exit /b 1
