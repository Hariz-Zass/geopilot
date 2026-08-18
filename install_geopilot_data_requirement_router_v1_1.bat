@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_geopilot_data_requirement_router_v1_1.ps1"
if errorlevel 1 (
  echo.
  echo DATA REQUIREMENT ROUTER V1.1 GATE FAILED
  exit /b 1
)
