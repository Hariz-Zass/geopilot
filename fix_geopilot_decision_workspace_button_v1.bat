@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_geopilot_decision_workspace_button_v1.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo FIX FAILED with exit code %RC%.
  echo Paste the complete output into ChatGPT.
) else (
  echo Fix completed successfully.
)
echo.
pause
exit /b %RC%
