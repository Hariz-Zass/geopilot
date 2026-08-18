@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "REPORT=geopilot_ai_terrain_orchestrator_source_v1.txt"

echo ============================================================ > "%REPORT%"
echo GEOPILOT AI TERRAIN ORCHESTRATOR SOURCE V1 >> "%REPORT%"
echo READ ONLY >> "%REPORT%"
echo ============================================================ >> "%REPORT%"

for %%F in (
 "backend\app\services\data_requirement_router.py"
 "backend\app\services\planning_orchestrator.py"
 "backend\app\services\grounded_synthesis.py"
 "backend\app\services\ai_providers.py"
 "backend\tests\test_data_requirement_router.py"
 "backend\tests\test_terrain_analysis.py"
 "frontend\src\features\planning\PlanningWorkspace.tsx"
 "frontend\src\lib\api\planningRuns.ts"
) do (
 echo. >> "%REPORT%"
 echo ============================================================ >> "%REPORT%"
 echo FILE: %%~F >> "%REPORT%"
 echo ============================================================ >> "%REPORT%"
 if exist "%%~F" (
   type "%%~F" >> "%REPORT%"
 ) else (
   echo MISSING >> "%REPORT%"
 )
)

echo. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo END - NO CHANGES MADE >> "%REPORT%"
echo ============================================================ >> "%REPORT%"

echo Audit complete:
echo %CD%\%REPORT%
pause
