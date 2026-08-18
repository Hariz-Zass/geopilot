@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_geopilot_isolated_live_acquired_document_e2e_v1.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo ACCEPTANCE FAILED with exit code %RC%.
  echo Do not rerun blindly. Paste the complete output into ChatGPT.
) else (
  echo Acceptance completed successfully.
)
echo.
pause
exit /b %RC%
