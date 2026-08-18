@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo GeoPilot Temporary E2E Terrain Acceptance V1
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_geopilot_temporary_e2e_terrain_acceptance_v1.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo ACCEPTANCE FAILED with exit code %RC%.
  echo Paste the complete sanitized output into ChatGPT.
) else (
  echo Acceptance completed successfully.
)
echo.
pause
exit /b %RC%
