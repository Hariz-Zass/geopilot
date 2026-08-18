@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect_trackb_mainland_relocation_preflight.ps1"
if errorlevel 1 (
  echo.
  echo MAINLAND RELOCATION PREFLIGHT FAILED
  exit /b 1
)
