@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "REPORT=geopilot_fixture_source_audit_v2.txt"

> "%REPORT%" (
  echo ============================================================
  echo GEOPILOT FIXTURE SOURCE AUDIT V2
  echo ============================================================
  echo Timestamp: %DATE% %TIME%
  echo Working directory: %CD%
  echo.
  echo [1] EXACT FIXTURE NAME SEARCH
)

powershell -NoProfile -Command ^
"$patterns = @('def session\(','def owner\(','def project\(','def site\(','@pytest\.fixture'); ^
Get-ChildItem 'backend\tests' -Recurse -File -Filter *.py | ForEach-Object { ^
  $p=$_.FullName; ^
  $lines=Get-Content $p; ^
  for($i=0;$i -lt $lines.Count;$i++){ ^
    foreach($pat in $patterns){ ^
      if($lines[$i] -match $pat){ ^
        $start=[Math]::Max(0,$i-3); $end=[Math]::Min($lines.Count-1,$i+20); ^
        '----- {0}:{1} -----' -f $p,($i+1); ^
        for($j=$start;$j -le $end;$j++){ '{0,4}: {1}' -f ($j+1),$lines[$j] }; ^
        ''; break ^
      } ^
    } ^
  } ^
}" >> "%REPORT%" 2>&1

>> "%REPORT%" (
  echo.
  echo [2] DATABASE / SESSION TEST PATTERNS
)

powershell -NoProfile -Command ^
"Get-ChildItem 'backend\tests' -Recurse -File -Filter *.py | Select-String -Pattern 'SessionLocal|sessionmaker|create_engine|DATABASE_URL|TestClient|override|get_db|StaticPool|sqlite|postgres' -Context 3,8 | ForEach-Object { $_.ToString(); '' }" >> "%REPORT%" 2>&1

>> "%REPORT%" (
  echo.
  echo [3] TERRAIN TEST CURRENT CONTENT
)

type "backend\tests\test_terrain_acquisition.py" >> "%REPORT%" 2>&1

>> "%REPORT%" (
  echo.
  echo ============================================================
  echo END AUDIT
  echo ============================================================
  echo No source, DB, migration, frontend, Docker lifecycle, or .env changes were made.
)

type "%REPORT%"
echo.
echo Report saved to:
echo %CD%\%REPORT%
echo.
pause
exit /b 0
