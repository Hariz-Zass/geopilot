@echo off
setlocal
echo ============================================================
echo GeoPilot Phase 2C.3B Controlled Commit Acceptance
echo REAL COMMIT - VERIFY - CLEANUP - BASELINE RESTORE
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_phase2c3b_controlled_commit_acceptance.ps1"
if errorlevel 1 (
 echo.
 echo ACCEPTANCE FAILED.
 echo Do not retry blindly. Send the result log to ChatGPT.
 pause
 exit /b 1
)
echo.
echo Acceptance completed successfully.
pause
