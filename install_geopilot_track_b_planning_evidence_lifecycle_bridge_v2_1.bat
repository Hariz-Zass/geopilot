@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_geopilot_track_b_planning_evidence_lifecycle_bridge_v2_1.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
 echo INSTALLER FAILED with exit code %RC%.
 echo Do not retry blindly. Paste the complete output into ChatGPT.
) else (
 echo Installer completed successfully.
)
echo.
pause
exit /b %RC%
