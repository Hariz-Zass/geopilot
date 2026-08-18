@echo off
setlocal
echo ============================================================
echo GeoPilot Smart Organizer Phase 2B.3
echo Generic Site Resolution Fallback and Confirmation Gate
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_geopilot_smart_organizer_phase2b3.ps1"
if errorlevel 1 (
 echo.
 echo INSTALLER FAILED.
 echo Do not retry blindly. Send the complete output to ChatGPT.
 pause
 exit /b 1
)
echo.
echo Installer completed successfully.
pause
