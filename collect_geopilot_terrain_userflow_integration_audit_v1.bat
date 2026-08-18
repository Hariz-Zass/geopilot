@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "REPORT=geopilot_terrain_userflow_integration_audit_v1.txt"

echo ============================================================ > "%REPORT%"
echo GEOPILOT TERRAIN USERFLOW INTEGRATION AUDIT V1 >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo Working directory: %CD% >> "%REPORT%"
echo. >> "%REPORT%"

echo [1] TERRAIN API ROUTE >> "%REPORT%"
if exist "backend\app\api\v1\terrain.py" type "backend\app\api\v1\terrain.py" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [2] TERRAIN ANALYSIS SERVICE >> "%REPORT%"
if exist "backend\app\services\terrain_analysis.py" type "backend\app\services\terrain_analysis.py" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [3] TERRAIN ACQUISITION SERVICE ENTRYPOINT >> "%REPORT%"
findstr /n /i /c:"def acquire_site_dem_if_missing" /c:"def preferred_site_dem" /c:"terrain_auto_acquisition_enabled" backend\app\services\terrain_acquisition.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [4] FRONTEND TERRAIN REFERENCES >> "%REPORT%"
findstr /s /n /i /c:"terrain" /c:"slope" /c:"elevation" frontend\src\*.ts frontend\src\*.tsx frontend\src\*.js frontend\src\*.jsx >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [5] TERRAIN TESTS >> "%REPORT%"
for %%F in (
 backend\tests\test_terrain_analysis.py
 backend\tests\test_terrain_acquisition.py
) do (
 if exist "%%F" (
  echo. >> "%REPORT%"
  echo ===== %%F ===== >> "%REPORT%"
  type "%%F" >> "%REPORT%"
 )
)

echo. >> "%REPORT%"
echo [6] API ROUTER REGISTRATION >> "%REPORT%"
findstr /s /n /i /c:"terrain" backend\app\api\*.py backend\app\api\v1\*.py backend\app\main.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo END AUDIT - READ ONLY >> "%REPORT%"
echo No source, DB, migration, frontend, Docker lifecycle, or .env changes were made. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"

type "%REPORT%"
echo.
echo Report saved to:
echo %CD%\%REPORT%
echo.
pause
exit /b 0
