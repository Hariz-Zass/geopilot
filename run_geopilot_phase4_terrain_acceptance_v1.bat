@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_geopilot_phase4_terrain_acceptance_v1.ps1"
if errorlevel 1 (
  echo.
  echo PHASE 4 TERRAIN ACCEPTANCE V1 FAILED
  exit /b 1
)
