@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_geopilot_terrain_explicit_site_v1_1.ps1"
if errorlevel 1 (
  echo.
  echo TERRAIN EXPLICIT-SITE FIX V1.1 FAILED
  exit /b 1
)
