@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect_geopilot_dem_ingestion_audit.ps1"
if errorlevel 1 (
  echo.
  echo DEM INGESTION AUDIT FAILED
  exit /b 1
)
