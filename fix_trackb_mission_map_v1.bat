@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_trackb_mission_map_v1.ps1"
if errorlevel 1 (
  echo.
  echo MAP PATCH GATE FAILED
  exit /b 1
)
