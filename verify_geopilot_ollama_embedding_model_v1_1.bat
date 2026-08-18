@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_geopilot_ollama_embedding_model_v1_1.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo VERIFICATION FAILED with exit code %RC%.
  echo Do not change config blindly. Paste the complete output into ChatGPT.
) else (
  echo Verification completed successfully.
)
echo.
pause
exit /b %RC%
