@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0remove_geopilot_closed_evidence_mode_v1_2.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
 echo REMOVAL FAILED with exit code %RC%.
 echo Do not retry blindly. Paste the complete output into ChatGPT.
) else (
 echo Removal completed successfully.
)
echo.
pause
exit /b %RC%
