@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo GeoPilot Manual DEM Regression Gate V1
echo Isolated test-harness verification
echo ============================================================
echo.

echo [1] Confirm test file exists
if not exist "backend\tests\test_terrain_acquisition.py" (
  echo BLOCKED: backend\tests\test_terrain_acquisition.py missing.
  pause
  exit /b 1
)

echo [2] Run manual DEM precedence test with its source module fixtures exposed
docker compose exec -T backend python -m pytest -q ^
  -p tests.test_task041_044 ^
  tests/test_terrain_acquisition.py::test_manual_dem_precedence

if errorlevel 1 (
  echo.
  echo BLOCKED: manual DEM precedence regression test still cannot pass.
  echo No live CDSE network acceptance should run yet.
  pause
  exit /b 1
)

echo.
echo [3] Run CDSE unit contract tests again
docker compose exec -T backend python -m pytest -q ^
  tests/test_terrain_acquisition.py::test_cdse_provider_uses_official_oauth_and_process_contract ^
  tests/test_terrain_acquisition.py::test_cdse_provider_rejects_failed_oauth

if errorlevel 1 (
  echo.
  echo BLOCKED: CDSE provider unit contract tests failed.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo MANUAL DEM + CDSE UNIT REGRESSION GATE PASS
echo ============================================================
echo Manual DEM precedence: PASS
echo CDSE OAuth/Process mocked contract: PASS
echo Source changed: NO
echo DB changed: NO
echo Migration created: NO
echo Frontend changed: NO
echo Live CDSE network acceptance: NOT RUN
echo ============================================================
echo.
pause
exit /b 0
