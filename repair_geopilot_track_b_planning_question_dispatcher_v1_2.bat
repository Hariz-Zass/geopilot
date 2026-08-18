@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0repair_geopilot_track_b_planning_question_dispatcher_v1_2.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
 echo REPAIR FAILED with exit code %RC%.
 echo Do not retry blindly. Paste the complete output into ChatGPT.
) else (
 echo Repair completed successfully.
)
echo.
pause
exit /b %RC%
