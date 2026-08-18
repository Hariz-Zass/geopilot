@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect_geopilot_capability_upgrade_audit.ps1"
if errorlevel 1 (
  echo.
  echo CAPABILITY AUDIT COLLECTION FAILED
  exit /b 1
)
