@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo GeoPilot CDSE Terrain Provider V1.1 Verification
echo Recovery for pytest import-path failure only
echo ============================================================
echo.

echo [1] Backend container path/import check
docker compose exec -T backend python -c "import os,sys; print('cwd:', os.getcwd()); print('app importable:', end=' '); import app; print('YES'); print('sys.path[0]:', sys.path[0])"
if errorlevel 1 (
  echo.
  echo BLOCKED: backend cannot import app package.
  pause
  exit /b 1
)

echo.
echo [2] Confirm CDSE provider patch exists
docker compose exec -T backend python -c "from app.services import terrain_acquisition as t; print('CDSE_TOKEN_URL present:', hasattr(t,'CDSE_TOKEN_URL')); print('Provider:', t.CopernicusDemProvider.name)"
if errorlevel 1 (
  echo.
  echo BLOCKED: patched terrain provider cannot be imported.
  pause
  exit /b 1
)

echo.
echo [3] Focused terrain tests via python -m pytest
docker compose exec -T backend python -m pytest -q tests/test_terrain_acquisition.py
if errorlevel 1 (
  echo.
  echo BLOCKED: focused terrain tests failed.
  echo Do not run live CDSE acceptance yet.
  pause
  exit /b 1
)

echo.
echo [4] Runtime config presence - secret values hidden
docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); print('CLIENT_ID configured:', bool(s.terrain_cdse_client_id)); print('CLIENT_SECRET configured:', bool(s.terrain_cdse_client_secret)); print('AUTO_ACQUISITION_ENABLED:', s.terrain_auto_acquisition_enabled); print('PROVIDER:', s.terrain_auto_provider)"
if errorlevel 1 (
  echo.
  echo BLOCKED: runtime config check failed.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo CDSE TERRAIN PROVIDER V1.1 VERIFICATION PASS
echo Source patch retained.
echo Focused tests pass through python -m pytest.
echo No DB change. No migration. No frontend change.
echo Live CDSE network acceptance has NOT been run.
echo ============================================================
echo.
pause
exit /b 0
