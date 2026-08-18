@echo off
setlocal
echo ============================================================
echo GeoPilot Smart Organizer Phase 2D.1.1
echo Frontend Controlled Import Workflow - TypeScript Repair
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_geopilot_smart_organizer_phase2d1_1.ps1"
if errorlevel 1 (
 echo.
 echo INSTALLER FAILED.
 echo Do not retry blindly. Send the complete output/log to ChatGPT.
 pause
 exit /b 1
)
echo.
echo Installer completed successfully.
pause
