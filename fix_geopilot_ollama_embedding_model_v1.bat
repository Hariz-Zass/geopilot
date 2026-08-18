@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_geopilot_ollama_embedding_model_v1.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo FIX FAILED with exit code %RC%.
  echo Do not retry blindly. Paste the complete output into ChatGPT.
) else (
  echo Fix completed successfully.
)
echo.
pause
exit /b %RC%
