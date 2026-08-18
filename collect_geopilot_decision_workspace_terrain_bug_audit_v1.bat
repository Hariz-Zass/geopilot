@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "REPORT=geopilot_decision_workspace_terrain_bug_audit_v1.txt"

echo ============================================================ > "%REPORT%"
echo GEOPILOT DECISION WORKSPACE TERRAIN BUG AUDIT V1 >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo Working directory: %CD% >> "%REPORT%"
echo. >> "%REPORT%"

echo [1] EXACT UI STRING SEARCH >> "%REPORT%"
findstr /s /n /i /c:"Build decision brief" /c:"From change detection to planner action" /c:"AI DECISION WORKSPACE" /c:"EVIDENCE LIMITED" frontend\src\*.ts frontend\src\*.tsx frontend\src\*.js frontend\src\*.jsx >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [2] TRACK B / DECISION API REFERENCES >> "%REPORT%"
findstr /s /n /i /c:"decision" /c:"planner_question" /c:"question" /c:"TEMPORAL_ANALYSIS" /c:"BEFORE_RASTER" /c:"AFTER_RASTER" backend\app\services\track_b*.py backend\app\api\v1\track_b.py frontend\src\lib\api\trackB.ts >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [3] LIKELY FRONTEND DECISION WORKSPACE FILES >> "%REPORT%"
for /r frontend\src %%F in (*.tsx *.ts) do (
  findstr /m /i /c:"Build decision brief" /c:"AI DECISION WORKSPACE" "%%F" >nul 2>&1
  if not errorlevel 1 (
    echo. >> "%REPORT%"
    echo ============================================================ >> "%REPORT%"
    echo FILE: %%F >> "%REPORT%"
    echo ============================================================ >> "%REPORT%"
    type "%%F" >> "%REPORT%"
  )
)

echo. >> "%REPORT%"
echo [4] TRACK B AI SOURCE >> "%REPORT%"
for %%F in (
 "backend\app\services\track_b_ai.py"
 "backend\app\services\track_b.py"
 "backend\app\api\v1\track_b.py"
 "frontend\src\lib\api\trackB.ts"
) do (
 if exist "%%~F" (
   echo. >> "%REPORT%"
   echo ============================================================ >> "%REPORT%"
   echo FILE: %%~F >> "%REPORT%"
   echo ============================================================ >> "%REPORT%"
   type "%%~F" >> "%REPORT%"
 )
)

echo. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo END AUDIT - READ ONLY >> "%REPORT%"
echo No source, DB, migration, frontend, Docker lifecycle, or .env changes were made. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"

echo Audit complete:
echo %CD%\%REPORT%
echo.
pause
exit /b 0
