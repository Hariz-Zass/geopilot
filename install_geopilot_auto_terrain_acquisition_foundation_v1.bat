@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_geopilot_auto_terrain_acquisition_foundation_v1.ps1"
if errorlevel 1 (
  echo.
  echo AUTO TERRAIN ACQUISITION FOUNDATION V1 GATE FAILED
  exit /b 1
)
