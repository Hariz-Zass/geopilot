@echo off
setlocal EnableExtensions DisableDelayedExpansion

REM ============================================================
REM GeoPilot AI - CDSE Terrain Provider Source Snapshot V1
REM READ-ONLY COLLECTOR
REM - Does NOT read .env
REM - Does NOT print credentials
REM - Does NOT modify source
REM - Does NOT touch DB / migrations / frontend
REM ============================================================

cd /d "%~dp0"

set "REPORT=geopilot_cdse_provider_source_snapshot_v1.txt"

> "%REPORT%" (
  echo ============================================================
  echo GEOPILOT CDSE TERRAIN PROVIDER SOURCE SNAPSHOT V1
  echo ============================================================
  echo Timestamp: %DATE% %TIME%
  echo Working directory: %CD%
  echo.
)

call :append_file "backend\app\services\terrain_acquisition.py"
call :append_file "backend\app\core\config.py"
call :append_file "backend\tests\test_terrain_acquisition.py"

if exist "backend\pyproject.toml" call :append_file "backend\pyproject.toml"
if exist "backend\requirements.txt" call :append_file "backend\requirements.txt"
if exist "backend\requirements-dev.txt" call :append_file "backend\requirements-dev.txt"
if exist "backend\Dockerfile" call :append_file "backend\Dockerfile"
if exist ".env.example" call :append_file ".env.example"
if exist "docker-compose.yml" call :append_file "docker-compose.yml"
if exist "docker-compose.override.yml" call :append_file "docker-compose.override.yml"

>> "%REPORT%" (
  echo.
  echo ============================================================
  echo RUNTIME CONFIG PRESENCE CHECK - VALUES NOT PRINTED
  echo ============================================================
)

docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); print('CLIENT_ID configured:', bool(s.terrain_cdse_client_id)); print('CLIENT_SECRET configured:', bool(s.terrain_cdse_client_secret)); print('AUTO_ACQUISITION_ENABLED:', s.terrain_auto_acquisition_enabled); print('PROVIDER:', s.terrain_auto_provider); print('TARGET_CRS:', s.terrain_auto_target_crs)" >> "%REPORT%" 2>&1

>> "%REPORT%" (
  echo.
  echo ============================================================
  echo END SNAPSHOT
  echo ============================================================
  echo .env was NOT read or copied.
  echo No source files were modified.
)

echo.
echo Source snapshot created:
echo %CD%\%REPORT%
echo.
echo Upload that TXT file to ChatGPT.
echo.
exit /b 0

:append_file
set "F=%~1"
>> "%REPORT%" (
  echo.
  echo ============================================================
  echo FILE: %F%
  echo ============================================================
)
if exist "%F%" (
  type "%F%" >> "%REPORT%"
) else (
  >> "%REPORT%" echo MISSING: %F%
)
>> "%REPORT%" echo.
exit /b 0
