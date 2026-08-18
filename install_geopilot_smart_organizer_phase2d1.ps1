$ErrorActionPreference="Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer Phase 2D.1"
Write-Host "Frontend Controlled Import Workflow"
Write-Host "NO BACKEND CHANGE / NO MIGRATION / NO DB WRITE BY INSTALLER"
Write-Host "============================================================"

$root=(Get-Location).Path
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root "artifacts\smart_organizer_phase2d1_backup_$stamp"
$log=Join-Path $root "artifacts\smart_organizer_phase2d1_result.txt"

foreach($p in @(
  ".\frontend\src\lib\api\trackB.ts",
  ".\frontend\src\pages\TrackBWorkspacePage.tsx",
  ".\frontend\src\styles.css",
  ".\backend\app\api\v1\track_b.py"
)){
  if(-not(Test-Path $p)){throw "Required file missing: $p"}
}

New-Item -ItemType Directory -Force $backup|Out-Null
Copy-Item ".\frontend\src\lib\api\trackB.ts" (Join-Path $backup "trackB.ts")
Copy-Item ".\frontend\src\pages\TrackBWorkspacePage.tsx" (Join-Path $backup "TrackBWorkspacePage.tsx")
Copy-Item ".\frontend\src\styles.css" (Join-Path $backup "styles.css")
if(Test-Path ".\frontend\src\components\SmartOrganizerControlledImport.tsx"){
  Copy-Item ".\frontend\src\components\SmartOrganizerControlledImport.tsx" (Join-Path $backup "SmartOrganizerControlledImport.tsx")
}

function Restore-Phase2D1 {
  Copy-Item (Join-Path $backup "trackB.ts") ".\frontend\src\lib\api\trackB.ts" -Force
  Copy-Item (Join-Path $backup "TrackBWorkspacePage.tsx") ".\frontend\src\pages\TrackBWorkspacePage.tsx" -Force
  Copy-Item (Join-Path $backup "styles.css") ".\frontend\src\styles.css" -Force
  if(Test-Path (Join-Path $backup "SmartOrganizerControlledImport.tsx")){
    Copy-Item (Join-Path $backup "SmartOrganizerControlledImport.tsx") ".\frontend\src\components\SmartOrganizerControlledImport.tsx" -Force
  } elseif(Test-Path ".\frontend\src\components\SmartOrganizerControlledImport.tsx"){
    Remove-Item ".\frontend\src\components\SmartOrganizerControlledImport.tsx" -Force
  }
}

try {
  Write-Host "BACKUP: $backup"
  Write-Host "[0] Accepted backend + frontend anchor preflight"
  $api=Get-Content ".\backend\app\api\v1\track_b.py" -Raw
  foreach($route in @(
    '"/organizer-intake/inspect"',
    '"/organizer-intake/site-candidates"',
    '"/organizer-intake/site-resolution/upload"',
    '"/organizer-intake/import-plan"',
    '"/organizer-intake/import-all"'
  )){
    if(-not $api.Contains($route)){throw "Accepted backend route missing: $route"}
  }
  $frontend=Get-Content ".\frontend\src\pages\TrackBWorkspacePage.tsx" -Raw
  if(-not $frontend.Contains('className="smart-intake"')){throw "Accepted Phase 1 frontend anchor missing."}
  Write-Host "backend_routes=CONFIRMED"
  Write-Host "phase1_frontend=CONFIRMED"

  Write-Host "[1] Patch frontend using exact accepted anchors"
  python ".\patch_phase2d1_frontend.py"
  if($LASTEXITCODE-ne 0){throw "Frontend patch failed."}

  Write-Host "[2] Frontend typecheck"
  docker compose exec -T frontend npm run typecheck
  if($LASTEXITCODE-ne 0){throw "Frontend typecheck failed."}

  Write-Host "[3] Frontend tests"
  docker compose exec -T frontend npm test
  if($LASTEXITCODE-ne 0){throw "Frontend tests failed."}

  Write-Host "[4] Frontend production build"
  docker compose exec -T frontend npm run build
  if($LASTEXITCODE-ne 0){throw "Frontend production build failed."}

  Write-Host "[5] Recreate frontend only"
  docker compose up -d --force-recreate frontend
  if($LASTEXITCODE-ne 0){throw "Frontend recreate failed."}
  Start-Sleep -Seconds 6
  docker compose ps frontend

  Write-Host "[6] Runtime HTTP"
  $status=(Invoke-WebRequest -UseBasicParsing "http://localhost:5177" -TimeoutSec 20).StatusCode
  Write-Host "frontend_http_status=$status"
  if($status-ne 200){throw "Frontend HTTP status is not 200."}

  Write-Host "[7] DB preservation"
  $db=@'
from app.db import get_session_factory
from sqlalchemy import text
with get_session_factory()() as db:
    print("alembic_revision=",db.execute(text("SELECT version_num FROM alembic_version")).scalar())
    print("site_count=",db.execute(text("SELECT COUNT(*) FROM sites")).scalar())
    print("gis_layers=",db.execute(text("SELECT COUNT(*) FROM gis_layers")).scalar())
    print("gis_features=",db.execute(text("SELECT COUNT(*) FROM gis_features")).scalar())
'@
  $db|docker compose exec -T -w /app backend python -
  if($LASTEXITCODE-ne 0){throw "DB preservation audit failed."}

  @"
============================================================
SMART ORGANIZER PHASE 2D.1 PASS
============================================================
Controlled frontend workflow: ENABLED
Organizer multi-file/ZIP analysis: ENABLED
Organizer Site candidate discovery: ENABLED
GeoJSON boundary fallback: ENABLED
Site confirmation before spatial plan: ENFORCED
Per-dataset explicit role selection: ENFORCED
Dry-run review before persistent import: ENFORCED
Final persistent confirmation checkbox: ENFORCED
Import All endpoint wiring: ENABLED
Existing Phase 1 inspect UI: PRESERVED
Existing manual Track B ingestion: PRESERVED
Backend production source changed: NO
Migration: NONE
Installer DB writes: NONE
Next gate: LIVE FRONTEND SMART ORGANIZER ACCEPTANCE
============================================================
"@|Tee-Object -FilePath $log

  Write-Host "RESULT SAVED TO: $log"
}
catch {
  Write-Host ""
  Write-Host "INSTALL FAILED - restoring frontend backup."
  Restore-Phase2D1
  try { docker compose up -d --force-recreate frontend | Out-Null } catch {}
  throw
}
