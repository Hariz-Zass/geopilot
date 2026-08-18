@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_geopilot_terrain_dem_ingestion_v1_3.ps1"
if errorlevel 1 (
  echo.
  echo TERRAIN DEM INGESTION V1.3 GATE FAILED
  exit /b 1
)
