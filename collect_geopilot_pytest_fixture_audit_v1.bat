@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "REPORT=geopilot_pytest_fixture_audit_v1.txt"

> "%REPORT%" (
  echo ============================================================
  echo GEOPILOT PYTEST FIXTURE AUDIT V1
  echo ============================================================
  echo Timestamp: %DATE% %TIME%
  echo Working directory: %CD%
  echo.
  echo [1] TEST TREE
)

dir /s /b backend\tests\*.py >> "%REPORT%" 2>&1

>> "%REPORT%" (
  echo.
  echo [2] CONFTEST FILES
)
dir /s /b backend\conftest.py backend\tests\conftest.py 2>> "%REPORT%" >> "%REPORT%"

>> "%REPORT%" (
  echo.
  echo [3] FIXTURE DECLARATIONS
)
powershell -NoProfile -Command "Get-ChildItem backend\tests -Recurse -File -Filter *.py | Select-String -Pattern '@pytest\.fixture|def session\(|def owner\(|def project\(|def site\(' | ForEach-Object { '{0}:{1}: {2}' -f $_.Path,$_.LineNumber,$_.Line.Trim() }" >> "%REPORT%" 2>&1

>> "%REPORT%" (
  echo.
  echo [4] PYTEST CONFIG FILES
)
for %%F in (backend\pytest.ini backend\pyproject.toml backend\setup.cfg pytest.ini pyproject.toml setup.cfg) do (
  if exist "%%F" (
    echo ----- %%F ----- >> "%REPORT%"
    type "%%F" >> "%REPORT%"
    echo. >> "%REPORT%"
  )
)

>> "%REPORT%" (
  echo.
  echo [5] NEW CDSE TESTS ONLY
)
docker compose exec -T backend python -m pytest -q ^
  tests/test_terrain_acquisition.py::test_cdse_provider_uses_official_oauth_and_process_contract ^
  tests/test_terrain_acquisition.py::test_cdse_provider_rejects_failed_oauth >> "%REPORT%" 2>&1

>> "%REPORT%" (
  echo.
  echo ============================================================
  echo END AUDIT
  echo ============================================================
  echo No source, DB, migration, frontend, or .env changes were made.
)

type "%REPORT%"
echo.
echo Report saved to:
echo %CD%\%REPORT%
echo.
pause
exit /b 0
