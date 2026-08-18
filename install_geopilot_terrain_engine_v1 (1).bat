@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_geopilot_terrain_engine_v1.ps1"
if errorlevel 1 (
  echo.
  echo TERRAIN ENGINE V1 GATE FAILED
  exit /b 1
)
