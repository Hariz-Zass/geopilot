@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect_geopilot_auto_terrain_acquisition_audit.ps1"
if errorlevel 1 (
  echo.
  echo AUTOMATIC TERRAIN ACQUISITION AUDIT FAILED
  exit /b 1
)
