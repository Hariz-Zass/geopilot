@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect_geopilot_embedding_provider_live_preflight_v1.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
 echo PREFLIGHT FOUND A BLOCKER with exit code %RC%.
 echo Paste the complete report into ChatGPT.
) else (
 echo Preflight completed successfully.
)
echo.
pause
exit /b %RC%
