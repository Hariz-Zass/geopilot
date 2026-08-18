@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "REPORT=geopilot_failed_to_fetch_diagnostic_v1.txt"

echo ============================================================ > "%REPORT%"
echo GEOPILOT FAILED-TO-FETCH DIAGNOSTIC V1 >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo Working directory: %CD% >> "%REPORT%"
echo. >> "%REPORT%"

echo [1] DOCKER SERVICE STATUS >> "%REPORT%"
docker compose ps >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [2] BACKEND HEALTH FROM HOST >> "%REPORT%"
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8007/health' -TimeoutSec 10; Write-Output ('HTTP ' + [int]$r.StatusCode); Write-Output $r.Content } catch { Write-Output ('ERROR: ' + $_.Exception.Message) }" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [3] BACKEND OPENAPI FROM HOST >> "%REPORT%"
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8007/openapi.json' -TimeoutSec 10; Write-Output ('HTTP ' + [int]$r.StatusCode); Write-Output ('bytes=' + $r.RawContentLength) } catch { Write-Output ('ERROR: ' + $_.Exception.Message) }" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [4] FRONTEND RUNTIME API BASE >> "%REPORT%"
docker compose exec -T frontend sh -lc "echo VITE_API_BASE_URL=$VITE_API_BASE_URL; echo VITE_APP_NAME=$VITE_APP_NAME" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [5] BACKEND RECENT LOGS >> "%REPORT%"
docker compose logs --tail=180 backend >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [6] FRONTEND RECENT LOGS >> "%REPORT%"
docker compose logs --tail=80 frontend >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [7] DECISION ENDPOINT ROUTE REGISTRATION >> "%REPORT%"
docker compose exec -T backend python -c "from app.main import app; [print(sorted(r.methods or []),r.path) for r in app.routes if 'decision-workspace' in r.path or 'planning-runs' in r.path]" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo END DIAGNOSTIC - READ ONLY >> "%REPORT%"
echo No source, DB, migration, or environment changes were made. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"

type "%REPORT%"
echo.
echo Report saved to:
echo %CD%\%REPORT%
echo.
pause
exit /b 0
