@echo off
setlocal
echo ============================================================
echo GeoPilot Smart Organizer Phase 2A
echo GIS Conversion Foundation + Import Plan
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_geopilot_smart_organizer_phase2a.ps1"
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
