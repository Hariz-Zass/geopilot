@echo off
setlocal
cd /d "%~dp0"
set "REPORT=geopilot_fixture_source_audit_v2_1.txt"

echo ============================================================ > "%REPORT%"
echo GEOPILOT FIXTURE SOURCE AUDIT V2.1 >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo Working directory: %CD% >> "%REPORT%"
echo. >> "%REPORT%"

echo [1] FIXTURE AND DATABASE PATTERN SEARCH >> "%REPORT%"
findstr /s /n /i /c:"def session(" /c:"def owner(" /c:"def project(" /c:"def site(" /c:"@pytest.fixture" /c:"SessionLocal" /c:"sessionmaker" /c:"get_db" /c:"create_engine" backend\tests\*.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [2] CURRENT TERRAIN TEST >> "%REPORT%"
type backend\tests\test_terrain_acquisition.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [3] SELECTED TEST FILES WITH FIXTURES >> "%REPORT%"
for %%F in (
 backend\tests\test_active_site_endpoint.py
 backend\tests\test_auth_foundation.py
 backend\tests\test_project_domain.py
 backend\tests\test_site_domain.py
 backend\tests\test_task041_044.py
) do (
 if exist "%%F" (
   echo. >> "%REPORT%"
   echo ===== %%F ===== >> "%REPORT%"
   type "%%F" >> "%REPORT%"
 )
)

echo. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo END AUDIT - READ ONLY >> "%REPORT%"
echo ============================================================ >> "%REPORT%"

echo Audit complete:
echo %CD%\%REPORT%
echo.
pause
exit /b 0
