@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo GeoPilot Basemap Attribution Type Fix V1
echo Fixes MapLibre TS2322 only
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p='.\frontend\src\pages\TrackBWorkspacePage.tsx';" ^
  "$t=Get-Content $p -Raw;" ^
  "if($t -notmatch 'attributionControl:\s*true'){ Write-Host 'BLOCKED: attributionControl: true not found'; exit 2 };" ^
  "$stamp=Get-Date -Format 'yyyyMMdd_HHmmss';" ^
  "$b='.\artifacts\trackb_basemap_attr_backup_'+$stamp;" ^
  "New-Item -ItemType Directory -Force -Path $b | Out-Null;" ^
  "Copy-Item $p ($b+'\TrackBWorkspacePage.tsx');" ^
  "$t=$t -replace 'attributionControl:\s*true','attributionControl: {}';" ^
  "Set-Content -Path $p -Value $t -Encoding UTF8;" ^
  "Write-Host ('BACKUP: '+$b);" ^
  "Write-Host 'PATCHED attributionControl: {}';"
if errorlevel 1 goto :fail

echo.
echo [1/3] TypeScript gate...
docker compose exec frontend npm run typecheck
if errorlevel 1 goto :fail

echo.
echo [2/3] Production build gate...
docker compose exec frontend npm run build
if errorlevel 1 goto :fail

echo.
echo [3/3] Restarting frontend...
docker compose restart frontend
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo BASEMAP ATTRIBUTION FIX PASS
echo Refresh GeoPilot with Ctrl+F5.
echo ============================================================
exit /b 0

:fail
echo.
echo ============================================================
echo BASEMAP ATTRIBUTION FIX FAILED
echo STOP and share this output.
echo ============================================================
exit /b 1
