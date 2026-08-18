@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0relocate_trackb_urban_to_shah_alam_v1.ps1"
if errorlevel 1 (
  echo.
  echo URBAN MAINLAND RELOCATION V1 GATE FAILED
  exit /b 1
)
