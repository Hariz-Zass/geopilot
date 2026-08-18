@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "REPORT=geopilot_planning_document_auto_acquisition_audit_v1.txt"

echo ============================================================ > "%REPORT%"
echo GEOPILOT PLANNING DOCUMENT AUTO-ACQUISITION AUDIT V1 >> "%REPORT%"
echo READ ONLY >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo Working directory: %CD% >> "%REPORT%"
echo. >> "%REPORT%"

echo [1] PLANNING DOCUMENT MODELS / SCHEMAS >> "%REPORT%"
for %%F in (
 "backend\app\models\planning_document.py"
 "backend\app\models\document.py"
 "backend\app\schemas\planning_document.py"
 "backend\app\schemas\document.py"
 "backend\app\schemas\document_retrieval.py"
) do (
 if exist "%%~F" (
  echo. >> "%REPORT%"
  echo ===== %%~F ===== >> "%REPORT%"
  type "%%~F" >> "%REPORT%"
 )
)

echo. >> "%REPORT%"
echo [2] DOCUMENT INGESTION / RETRIEVAL SERVICES >> "%REPORT%"
for %%F in (
 "backend\app\services\documents.py"
 "backend\app\services\document_ingestion.py"
 "backend\app\services\document_retrieval.py"
 "backend\app\services\planning_documents.py"
 "backend\app\services\ocr.py"
) do (
 if exist "%%~F" (
  echo. >> "%REPORT%"
  echo ===== %%~F ===== >> "%REPORT%"
  type "%%~F" >> "%REPORT%"
 )
)

echo. >> "%REPORT%"
echo [3] DOCUMENT API ROUTES >> "%REPORT%"
findstr /s /n /i /c:"PlanningDocument" /c:"upload" /c:"document" /c:"search" backend\app\api\v1\*.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [4] PROVIDER / HTTP / ACQUISITION REFERENCES >> "%REPORT%"
findstr /s /n /i /c:"httpx" /c:"requests" /c:"provider" /c:"source_url" /c:"download" /c:"acquisition" backend\app\services\*.py backend\app\core\*.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [5] DOCUMENT TESTS >> "%REPORT%"
findstr /s /n /i /c:"planning_document" /c:"document" /c:"search_documents" /c:"upload" backend\tests\*.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [6] MIGRATION / TABLE REFERENCES >> "%REPORT%"
findstr /s /n /i /c:"planning_documents" /c:"document_chunks" /c:"document_pages" backend\alembic\versions\*.py backend\migrations\versions\*.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [7] CURRENT ENVIRONMENT KEYS RELEVANT TO DOCUMENT ACQUISITION >> "%REPORT%"
findstr /n /i /c:"DOCUMENT" /c:"HTTP" /c:"PLANMALAYSIA" /c:"MYPLAN" .env.example >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo END AUDIT - NO CHANGES MADE >> "%REPORT%"
echo ============================================================ >> "%REPORT%"

type "%REPORT%"
echo.
echo Report saved to:
echo %CD%\%REPORT%
echo.
pause
exit /b 0
