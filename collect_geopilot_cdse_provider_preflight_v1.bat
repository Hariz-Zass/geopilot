@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM GeoPilot AI - CDSE Terrain Provider Acceptance Preflight V1
REM SAFE AUDIT ONLY
REM - No DB changes
REM - No migration
REM - No frontend changes
REM - No container restart/recreate
REM - No secret values printed
REM ============================================================

cd /d "%~dp0"

set "REPORT=geopilot_cdse_provider_preflight_audit.txt"

(
echo ============================================================
echo GEOPILOT CDSE TERRAIN PROVIDER ACCEPTANCE PREFLIGHT V1
echo ============================================================
echo Timestamp: %DATE% %TIME%
echo Working directory: %CD%
echo.

echo [1] PROJECT ROOT CHECK
if exist "docker-compose.yml" (
    echo docker-compose.yml: FOUND
) else (
    echo docker-compose.yml: MISSING
)
if exist "backend\app\core\config.py" (
    echo backend config: FOUND
) else (
    echo backend config: MISSING
)
if exist "backend\app\services\terrain_acquisition.py" (
    echo terrain acquisition service: FOUND
) else (
    echo terrain acquisition service: MISSING
)
echo.

echo [2] GIT METADATA CHECK
if exist ".git" (
    echo Git metadata: PRESENT
    git rev-parse HEAD 2^>nul
    git status --short 2^>nul
) else (
    echo GIT SAFETY CHECK: UNAVAILABLE - WORKING COPY HAS NO .git METADATA
)
echo.

echo [3] DOCKER SERVICE STATUS
docker compose ps
echo.

echo [4] BACKEND CONFIG PRESENCE - VALUES ARE NOT PRINTED
docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); print('CLIENT_ID configured:', bool(s.terrain_cdse_client_id)); print('CLIENT_SECRET configured:', bool(s.terrain_cdse_client_secret)); print('AUTO_ACQUISITION_ENABLED:', s.terrain_auto_acquisition_enabled); print('PROVIDER:', s.terrain_auto_provider); print('TARGET_CRS:', s.terrain_auto_target_crs)"
echo.

echo [5] TERRAIN CONFIG DECLARATIONS
powershell -NoProfile -Command "Select-String -Path 'backend\app\core\config.py' -Pattern 'TERRAIN_AUTO_|TERRAIN_CDSE_' -Context 1,1 | ForEach-Object { $_.ToString() }"
echo.

echo [6] COPERNICUS PROVIDER IMPLEMENTATION
powershell -NoProfile -Command "Select-String -Path 'backend\app\services\terrain_acquisition.py' -Pattern 'class CopernicusDemProvider|copernicus_cdse|terrain_cdse_client_id|terrain_cdse_client_secret|network acquisition|provider acceptance|def acquire' -Context 3,3 | ForEach-Object { $_.ToString() }"
echo.

echo [7] MANUAL DEM PRIORITY / AUTO FALLBACK PATH
powershell -NoProfile -Command "Select-String -Path 'backend\app\services\terrain_acquisition.py' -Pattern 'manual|ready Site DEM|automatic terrain acquisition|provider.acquire|site_scope|DEM' -Context 2,2 | Select-Object -First 140 | ForEach-Object { $_.ToString() }"
echo.

echo [8] HTTP / RASTER DEPENDENCY PROBE
docker compose exec -T backend python -c "import importlib.util as i; mods=['httpx','requests','rasterio','numpy','pyproj','shapely']; [print(m+':', 'YES' if i.find_spec(m) else 'NO') for m in mods]"
echo.

echo [9] TERRAIN TEST DISCOVERY
if exist "backend\tests\test_terrain_acquisition.py" (
    echo backend\tests\test_terrain_acquisition.py: FOUND
    powershell -NoProfile -Command "Select-String -Path 'backend\tests\test_terrain_acquisition.py' -Pattern '^def test_|Copernicus|manual|provider|acquisition' | ForEach-Object { $_.ToString() }"
) else (
    echo backend\tests\test_terrain_acquisition.py: MISSING
)
echo.

echo [10] ENV EXAMPLE TERRAIN PLACEHOLDERS ONLY
if exist ".env.example" (
    powershell -NoProfile -Command "Select-String -Path '.env.example' -Pattern 'TERRAIN_' | ForEach-Object { $_.ToString() }"
) else (
    echo .env.example: MISSING
)
echo.

echo [11] SECRET-SAFE SOURCE SCAN
echo NOTE: This checks for suspicious hard-coded assignments in source files.
echo It does NOT read or print .env.
powershell -NoProfile -Command "$files = Get-ChildItem backend -Recurse -File -Include *.py,*.yml,*.yaml,*.json,*.toml,*.ini,*.txt,*.md -ErrorAction SilentlyContinue; $hits = $files | Select-String -Pattern 'TERRAIN_CDSE_CLIENT_SECRET\s*=\s*[\"''][^\"'']+[\"'']|Authorization\s*[:=]\s*[\"'']Bearer\s+[A-Za-z0-9_\-\.]+' -ErrorAction SilentlyContinue; if($hits){$hits | ForEach-Object { '{0}:{1}: SUSPICIOUS_MATCH' -f $_.Path,$_.LineNumber }} else { 'No obvious hard-coded CDSE secret/token pattern found in scanned source files.' }"
echo.

echo ============================================================
echo PREFLIGHT COMPLETE
echo ============================================================
echo This script made NO source, DB, migration, frontend, or Docker lifecycle changes.
echo Review this report before implementing the live CDSE provider acceptance gate.
echo ============================================================
) > "%REPORT%" 2>&1

type "%REPORT%"

echo.
echo Report saved to:
echo %CD%\%REPORT%
echo.
pause
endlocal
