@echo off
setlocal
echo ============================================================
echo GeoPilot FINAL Judge Demo Acceptance
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_final_judge_demo_acceptance.ps1"
set EC=%ERRORLEVEL%
echo.
if not "%EC%"=="0" (
  echo FINAL ACCEPTANCE BLOCKED.
  echo Do not rerun blindly. Upload artifacts\final_judge_demo_acceptance.txt to ChatGPT.
) else (
  echo FINAL ACCEPTANCE COMPLETED.
  echo Upload artifacts\final_judge_demo_acceptance.txt to ChatGPT for verification.
)
pause
exit /b %EC%
