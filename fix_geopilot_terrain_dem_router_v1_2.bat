@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_geopilot_terrain_dem_router_v1_2.ps1"
if errorlevel 1 (
  echo.
  echo TERRAIN DEM INGESTION V1.2 GATE FAILED
  exit /b 1
)
