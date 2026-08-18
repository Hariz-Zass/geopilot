@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo GeoPilot Track B OpenAI Contract Fix V1
echo backup ^> patch ^> compile ^> tests ^> restart ^> verify
echo ============================================================
echo.

if not exist "fix_trackb_openai_contract.ps1" (
  echo BLOCKED: fix_trackb_openai_contract.ps1 must be beside this BAT.
  exit /b 1
)

docker compose config --services >nul 2>&1
if errorlevel 1 (
  echo BLOCKED: run these files from the geopilot_v7 project root.
  exit /b 1
)

echo [1/5] Applying controlled patch...
powershell -NoProfile -ExecutionPolicy Bypass -File ".\fix_trackb_openai_contract.ps1"
if errorlevel 1 goto :fail

echo.
echo [2/5] Compiling patched backend...
docker compose exec backend python -m compileall app/services/track_b_ai.py tests/test_track_b_hackathon.py
if errorlevel 1 goto :fail

echo.
echo [3/5] Running Track B regression suite...
docker compose exec -e PYTHONPATH=/app backend pytest -q tests/test_track_b_hackathon.py
if errorlevel 1 goto :fail

echo.
echo [4/5] Recreating backend...
docker compose up -d --force-recreate backend
if errorlevel 1 goto :fail

timeout /t 5 /nobreak >nul

echo.
echo [5/5] Verifying provider order...
docker compose exec -T backend python -c "from app.core.config import get_settings; from app.services.provider_resilience import _provider_order; s=get_settings(); print('PRIMARY=',s.ai_provider); print('FALLBACK=',s.ai_fallback_provider); print('ORDER=',[p.name for p in _provider_order(s)]); print('CONTRACT_PATCH=V1')"
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo PATCH GATE PASS
echo Run ONE Full Track B Mission in the UI.
echo If it is not 7/7, do not rerun; share the execution trace.
echo ============================================================
exit /b 0

:fail
echo.
echo ============================================================
echo PATCH GATE FAILED
echo STOP. Backup is under artifacts\trackb_contract_backup_*
echo Share this terminal output before making more changes.
echo ============================================================
exit /b 1
