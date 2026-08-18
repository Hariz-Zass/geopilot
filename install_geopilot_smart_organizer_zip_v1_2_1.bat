@echo off
setlocal
echo ============================================================
echo GeoPilot Smart Organizer ZIP V1.2.1 Repair
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_geopilot_smart_organizer_zip_v1_2_1.ps1"
if errorlevel 1 (
 echo.
 echo INSTALLER FAILED.
 echo Do not retry blindly. Send the complete output to ChatGPT.
 pause
 exit /b 1
)
echo.
echo Installer completed successfully.
pause
