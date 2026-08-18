@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "REPORT=geopilot_ai_terrain_tool_integration_audit_v1.txt"

echo ============================================================ > "%REPORT%"
echo GEOPILOT AI TERRAIN TOOL INTEGRATION AUDIT V1 >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo Working directory: %CD% >> "%REPORT%"
echo. >> "%REPORT%"

echo [1] PLANNING / AI TOOL REGISTRY >> "%REPORT%"
if exist "backend\app\services\planning_tools.py" type "backend\app\services\planning_tools.py" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [2] AI / PLANNING SERVICE REFERENCES >> "%REPORT%"
findstr /s /n /i /c:"get_tool(" /c:"terrain.site_summary" /c:"tool" /c:"planning" /c:"chat" /c:"intent" backend\app\services\*.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [3] AI / CHAT API ROUTES >> "%REPORT%"
findstr /s /n /i /c:"chat" /c:"assistant" /c:"planning" /c:"tool" backend\app\api\v1\*.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [4] TERRAIN ANALYSIS TOOL TESTS >> "%REPORT%"
findstr /s /n /i /c:"terrain.site_summary" /c:"terrain" /c:"tool_registry" backend\tests\*.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [5] LIKELY AI ORCHESTRATION FILES >> "%REPORT%"
for %%F in (
 backend\app\services\planning_agent.py
 backend\app\services\planning.py
 backend\app\services\planning_officer.py
 backend\app\services\agent.py
 backend\app\services\ai.py
 backend\app\services\llm.py
 backend\app\api\v1\planning.py
 backend\app\api\v1\planning_runs.py
 backend\app\api\v1\chat.py
 backend\app\api\v1\assistant.py
) do (
 if exist "%%F" (
  echo. >> "%REPORT%"
  echo ===== %%F ===== >> "%REPORT%"
  type "%%F" >> "%REPORT%"
 )
)

echo. >> "%REPORT%"
echo [6] FRONTEND AI / CHAT REFERENCES >> "%REPORT%"
findstr /s /n /i /c:"chat" /c:"assistant" /c:"planning" /c:"terrain" frontend\src\*.ts frontend\src\*.tsx frontend\src\*.js frontend\src\*.jsx >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo END AUDIT - READ ONLY >> "%REPORT%"
echo No source, DB, migration, frontend, Docker lifecycle, or .env changes were made. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"

type "%REPORT%"
echo.
echo Report saved to:
echo %CD%\%REPORT%
echo.
pause
exit /b 0
