@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo GeoPilot Site Applicability SQL Lifecycle V1.1 Recovery
echo Clean recovery from failed interactive installer attempt
echo NO DB DATA UPDATE / NO MIGRATION / NO FRONTEND CHANGE
echo ============================================================

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"
set "BACKUP=artifacts\site_applicability_sql_lifecycle_v1_1_backup_%STAMP%"
mkdir "%BACKUP%" >nul 2>&1

if not exist "backend\app\services\site_applicability.py" (
  echo ERROR: target source not found.
  exit /b 1
)

copy /Y "backend\app\services\site_applicability.py" "%BACKUP%\site_applicability.py" >nul
if errorlevel 1 (
  echo ERROR: backup failed.
  exit /b 1
)

echo BACKUP: %CD%\%BACKUP%

echo [0] Confirm clean original state
findstr /C:"AND s.is_active IS TRUE" "backend\app\services\site_applicability.py" >nul
if errorlevel 1 (
  echo ERROR: expected hardcoded ACTIVE SQL gate not found.
  goto :restore
)
findstr /C:"require_active" "backend\app\services\site_applicability.py" >nul
if not errorlevel 1 (
  echo ERROR: partial lifecycle patch detected.
  goto :restore
)
echo preflight_state=CONFIRMED

echo [1] Stage validated patcher and test
copy /Y "%~dp0patch_geopilot_site_applicability_sql_lifecycle_v1_1.py" "backend\_patch_geopilot_site_applicability_sql_lifecycle_v1_1.py" >nul
if errorlevel 1 goto :restore
copy /Y "%~dp0test_site_applicability_sql_lifecycle_v1_1.py" "backend\tests\test_site_applicability_sql_lifecycle_v1_1.py" >nul
if errorlevel 1 goto :restore

echo [2] Patcher syntax check
docker compose exec -T backend python -m py_compile /app/_patch_geopilot_site_applicability_sql_lifecycle_v1_1.py
if errorlevel 1 goto :restore

echo [3] Apply SQL lifecycle patch
docker compose exec -T backend python /app/_patch_geopilot_site_applicability_sql_lifecycle_v1_1.py
if errorlevel 1 goto :restore

echo [4] Backend syntax checks
docker compose exec -T backend python -m py_compile app/services/site_applicability.py tests/test_site_applicability_sql_lifecycle_v1_1.py
if errorlevel 1 goto :restore

echo [5] Focused regression
docker compose exec -T backend python -m pytest -q tests/test_site_applicability_sql_lifecycle_v1_1.py
if errorlevel 1 goto :restore

echo [6] Preserve prior regressions
for %%T in (
  tests/test_track_b_planning_evidence_lifecycle_bridge_v2_3.py
  tests/test_planning_question_multi_evidence_router_v1_2.py
  tests/test_planning_spatial_evidence_foundation_v1.py
  tests/test_auto_research_evidence_scope_bridge_v2.py
) do (
  if exist "backend\%%T" (
    docker compose exec -T backend python -m pytest -q %%T
    if errorlevel 1 goto :restore
  )
)

echo [7] Recreate backend
docker compose up -d --no-deps --force-recreate backend
if errorlevel 1 goto :restore

timeout /t 5 /nobreak >nul

echo [8] Runtime source verification
docker compose exec -T backend python -c "from pathlib import Path; t=Path('/app/app/services/site_applicability.py').read_text(); assert 'CAST(:require_active AS boolean) IS FALSE' in t; assert '\"require_active\": site_state is SiteState.ACTIVE' in t; assert 'AND s.is_archived IS FALSE' in t; print('runtime_sql_lifecycle=PASS')"
if errorlevel 1 goto :restore

echo [9] Backend health
docker compose ps backend

del /Q "backend\_patch_geopilot_site_applicability_sql_lifecycle_v1_1.py" >nul 2>&1

echo ============================================================
echo SITE APPLICABILITY SQL LIFECYCLE V1.1 PASS
echo ============================================================
echo Explicit AVAILABLE SiteState in SQL: ENABLED
echo Default ACTIVE requirement: PRESERVED
echo Archived Site rejection: PRESERVED
echo Project/site identity filters: PRESERVED
echo DB data change: NONE
echo DB schema change: NONE
echo Migration: NONE
echo Frontend change: NONE
echo Next gate: RERUN PLANNING SPATIAL ACCEPTANCE FIXTURE
echo ============================================================
echo.
pause
exit /b 0

:restore
echo.
echo INSTALL FAILED - restoring source backup.
copy /Y "%BACKUP%\site_applicability.py" "backend\app\services\site_applicability.py" >nul
del /Q "backend\_patch_geopilot_site_applicability_sql_lifecycle_v1_1.py" >nul 2>&1
del /Q "backend\tests\test_site_applicability_sql_lifecycle_v1_1.py" >nul 2>&1
echo Do not retry blindly. Paste the complete output into ChatGPT.
echo.
pause
exit /b 1
