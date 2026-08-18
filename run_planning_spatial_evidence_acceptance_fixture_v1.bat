@echo off
setlocal
cd /d "%~dp0"

set "PROJECT_ID=f7617e94-7d8c-47d0-8bed-635cf2f48579"
set "SITE_ID=2ea1e98d-347c-4a0a-8e5b-5dd7f9553673"

copy /Y "%~dp0run_planning_spatial_evidence_acceptance_fixture_v1.py" "backend\_run_planning_spatial_evidence_acceptance_fixture_v1.py" >nul
if errorlevel 1 (
  echo Failed to stage acceptance runner.
  pause
  exit /b 1
)

docker compose exec -T backend python -m py_compile /app/_run_planning_spatial_evidence_acceptance_fixture_v1.py
if errorlevel 1 (
  del /Q "backend\_run_planning_spatial_evidence_acceptance_fixture_v1.py" 2>nul
  echo Acceptance runner syntax check failed.
  pause
  exit /b 1
)

docker compose exec -T backend python /app/_run_planning_spatial_evidence_acceptance_fixture_v1.py --project-id %PROJECT_ID% --site-id %SITE_ID%
set "RC=%ERRORLEVEL%"

del /Q "backend\_run_planning_spatial_evidence_acceptance_fixture_v1.py" 2>nul

echo.
if not "%RC%"=="0" (
  echo ACCEPTANCE FIXTURE FAILED with exit code %RC%.
  echo Paste the complete output into ChatGPT.
) else (
  echo ACCEPTANCE FIXTURE COMPLETED.
  echo The synthetic GIS layer and feature were deleted after verification.
)
echo.
pause
exit /b %RC%
