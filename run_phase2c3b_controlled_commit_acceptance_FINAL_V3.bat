@echo off
setlocal
echo ============================================================
echo GeoPilot Phase 2C.3B Controlled Commit Acceptance FINAL V3
echo GeoPackage Feature.id-safe repair
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_phase2c3b_controlled_commit_acceptance_FINAL_V3.ps1"
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" (
  echo ACCEPTANCE BLOCKED.
  echo Send artifacts\phase_2c3b_controlled_commit_acceptance_FINAL_V3.txt to ChatGPT.
) else (
  echo ACCEPTANCE PASS.
)
pause
exit /b %ERR%
