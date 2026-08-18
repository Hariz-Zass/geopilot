@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect_geopilot_pdf_ingestion_source_audit_v1.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
 echo AUDIT FAILED with exit code %RC%.
 echo Paste the complete report into ChatGPT.
) else (
 echo Audit completed successfully.
)
echo.
pause
exit /b %RC%
