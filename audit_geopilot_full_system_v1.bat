@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0audit_geopilot_full_system_v1.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
 echo AUDIT FAILED with exit code %RC%.
 echo Paste the complete console output into ChatGPT.
) else (
 echo Audit completed successfully.
 echo Send geopilot_full_system_audit_v1.txt to ChatGPT.
)
echo.
pause
exit /b %RC%
