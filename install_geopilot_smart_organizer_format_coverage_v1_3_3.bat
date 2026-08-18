@echo off
setlocal
echo ============================================================
echo GeoPilot Smart Organizer Format Coverage V1.3.3
echo Runtime-verification quoting repair
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_geopilot_smart_organizer_format_coverage_v1_3_3.ps1"
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
