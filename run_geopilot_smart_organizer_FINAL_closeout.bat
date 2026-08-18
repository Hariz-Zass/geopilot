@echo off
setlocal
echo ============================================================
echo GeoPilot Smart Organizer FINAL Judge-Ready Closeout
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_geopilot_smart_organizer_FINAL_closeout.ps1"
if errorlevel 1 (
 echo.
 echo CLOSEOUT BLOCKED.
 echo Do not rerun blindly. Send the output/log to ChatGPT.
 pause
 exit /b 1
)
echo.
echo CLOSEOUT PASS.
pause
