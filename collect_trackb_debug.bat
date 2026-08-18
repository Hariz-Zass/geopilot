@echo off
setlocal

cd /d "%~dp0"

set "OUT=trackb_debug_bundle.txt"

echo ================================================== > "%OUT%"
echo GEOPILOT TRACK B DEBUG BUNDLE >> "%OUT%"
echo ================================================== >> "%OUT%"
echo. >> "%OUT%"

echo [1] provider_resilience.py >> "%OUT%"
echo ================================================== >> "%OUT%"
type backend\app\services\provider_resilience.py >> "%OUT%"
echo. >> "%OUT%"

echo [2] track_b_ai.py >> "%OUT%"
echo ================================================== >> "%OUT%"
type backend\app\services\track_b_ai.py >> "%OUT%"
echo. >> "%OUT%"

echo [3] track_b_workflow.py >> "%OUT%"
echo ================================================== >> "%OUT%"
type backend\app\services\track_b_workflow.py >> "%OUT%"
echo. >> "%OUT%"

echo [4] track_b_acceptance.py >> "%OUT%"
echo ================================================== >> "%OUT%"
type backend\app\services\track_b_acceptance.py >> "%OUT%"
echo. >> "%OUT%"

echo [5] schemas\track_b.py >> "%OUT%"
echo ================================================== >> "%OUT%"
type backend\app\schemas\track_b.py >> "%OUT%"
echo. >> "%OUT%"

echo [6] ai_providers.py >> "%OUT%"
echo ================================================== >> "%OUT%"
type backend\app\services\ai_providers.py >> "%OUT%"
echo. >> "%OUT%"

echo [7] config.py >> "%OUT%"
echo ================================================== >> "%OUT%"
type backend\app\core\config.py >> "%OUT%"
echo. >> "%OUT%"

echo [8] Track B tests >> "%OUT%"
echo ================================================== >> "%OUT%"
type backend\tests\test_track_b_hackathon.py >> "%OUT%"
echo. >> "%OUT%"

echo [9] Track B API route >> "%OUT%"
echo ================================================== >> "%OUT%"
type backend\app\api\v1\track_b.py >> "%OUT%"
echo. >> "%OUT%"

echo [10] Current non-secret AI config >> "%OUT%"
echo ================================================== >> "%OUT%"
docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); print('AI_PROVIDER=',s.ai_provider); print('AI_FALLBACK_PROVIDER=',s.ai_fallback_provider); print('OPENAI_KEY=','SET' if s.openai_api_key else 'NOT SET'); print('OPENAI_MODEL=',s.openai_planning_model); print('OLLAMA_MODEL=',s.ollama_planning_model)" >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo [11] Provider order >> "%OUT%"
echo ================================================== >> "%OUT%"
docker compose exec -T backend python -c "from app.core.config import get_settings; from app.services.provider_resilience import _provider_order; s=get_settings(); print([p.name for p in _provider_order(s)])" >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo [12] Track B regression tests >> "%OUT%"
echo ================================================== >> "%OUT%"
docker compose exec -e PYTHONPATH=/app backend pytest -q tests/test_track_b_hackathon.py >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo ================================================== >> "%OUT%"
echo END DEBUG BUNDLE >> "%OUT%"
echo ================================================== >> "%OUT%"

echo.
echo DONE
echo Generated: %CD%\%OUT%
echo.
pause
