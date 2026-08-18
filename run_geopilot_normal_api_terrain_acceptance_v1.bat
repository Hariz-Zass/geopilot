@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_geopilot_normal_api_terrain_acceptance_v1.ps1"
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
