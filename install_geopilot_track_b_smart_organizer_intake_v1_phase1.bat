@echo off
setlocal
echo ============================================================
echo GeoPilot Track B Smart Organizer Intake V1 - Phase 1
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_geopilot_track_b_smart_organizer_intake_v1_phase1.ps1"
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
