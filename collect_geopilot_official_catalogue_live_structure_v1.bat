@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "PYFILE=collect_geopilot_official_catalogue_live_structure_v1.py"
set "REPORT=geopilot_official_catalogue_live_structure_v1.txt"

if not exist "%PYFILE%" (
  echo ERROR: %PYFILE% not found beside this BAT file.
  pause
  exit /b 1
)

echo ============================================================
echo GeoPilot Official Catalogue Live Structure V1
echo READ ONLY - NO DB / MIGRATION / SOURCE PATCH
echo ============================================================
echo.

docker compose exec -T backend python "/app/%PYFILE%" > "%REPORT%" 2>&1
set "RC=%ERRORLEVEL%"

type "%REPORT%"

echo.
echo Report saved to:
echo %CD%\%REPORT%
echo.

if not "%RC%"=="0" (
  echo AUDIT FAILED with exit code %RC%.
  echo Paste the complete report into ChatGPT.
) else (
  echo Audit completed successfully.
)

echo.
pause
exit /b %RC%
