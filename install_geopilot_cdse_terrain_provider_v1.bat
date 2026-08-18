@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo GeoPilot CDSE Terrain Provider V1 Installer
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_geopilot_cdse_terrain_provider_v1.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo INSTALLER FAILED with exit code %RC%.
  echo Review the PowerShell error above. Do not retry blindly.
) else (
  echo Installer completed successfully.
)
echo.
pause
exit /b %RC%
