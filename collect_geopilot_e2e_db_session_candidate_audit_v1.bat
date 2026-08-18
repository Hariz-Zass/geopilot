@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "REPORT=geopilot_e2e_db_session_candidate_audit_v1.txt"

echo ============================================================ > "%REPORT%"
echo GEOPILOT E2E DB SESSION + SITE CANDIDATE AUDIT V1 >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo Working directory: %CD% >> "%REPORT%"
echo. >> "%REPORT%"

echo [1] DB MODULE SOURCE >> "%REPORT%"
if exist "backend\app\db\session.py" type backend\app\db\session.py >> "%REPORT%" 2>&1
if exist "backend\app\db\__init__.py" (
 echo. >> "%REPORT%"
 echo ----- backend\app\db\__init__.py ----- >> "%REPORT%"
 type backend\app\db\__init__.py >> "%REPORT%" 2>&1
)

echo. >> "%REPORT%"
echo [2] SESSION FACTORY REFERENCES >> "%REPORT%"
findstr /s /n /i /c:"sessionmaker" /c:"SessionLocal" /c:"get_db" /c:"Session(" backend\app\*.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [3] MODEL TABLE/COLUMN SNAPSHOT >> "%REPORT%"
docker compose exec -T backend python -c "from app.models.project import Project; from app.models.site import Site; from app.models.raster import RasterDataset; print('Project columns:', [c.name for c in Project.__table__.columns]); print('Site columns:', [c.name for c in Site.__table__.columns]); print('RasterDataset columns:', [c.name for c in RasterDataset.__table__.columns])" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [4] DB ENGINE / SESSION DISCOVERY >> "%REPORT%"
docker compose exec -T backend python -c "import app.db.session as m; print('module:',m.__name__); print('public:',[x for x in dir(m) if not x.startswith('_')])" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo END AUDIT - READ ONLY >> "%REPORT%"
echo No DB write, raster write, migration, frontend change, or credential output was performed. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"

type "%REPORT%"
echo.
echo Report saved to:
echo %CD%\%REPORT%
echo.
pause
exit /b 0
