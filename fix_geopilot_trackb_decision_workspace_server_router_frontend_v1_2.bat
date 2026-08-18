@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_geopilot_trackb_decision_workspace_server_router_frontend_v1_2.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo FIX FAILED with exit code %RC%.
  echo Do not retry blindly. Paste the complete output into ChatGPT.
) else (
  echo Fix completed successfully.
)
echo.
pause
exit /b %RC%
