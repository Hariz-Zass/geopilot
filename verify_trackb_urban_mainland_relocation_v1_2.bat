@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_trackb_urban_mainland_relocation_v1_2.ps1"
if errorlevel 1 (
  echo.
  echo URBAN MAINLAND RELOCATION V1.2 POST-VERIFY FAILED
  exit /b 1
)
