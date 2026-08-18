$ErrorActionPreference="Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer FINAL Judge-Ready Closeout"
Write-Host "REGRESSION + RUNTIME + DB PRESERVATION"
Write-Host "NO SOURCE WRITE / NO MIGRATION / NO DB WRITE"
Write-Host "============================================================"

$root=(Get-Location).Path
$log=Join-Path $root "artifacts\smart_organizer_FINAL_judge_ready_closeout.txt"
New-Item -ItemType Directory -Force (Join-Path $root "artifacts") | Out-Null

"============================================================" | Set-Content $log
"GEOPILOT SMART ORGANIZER FINAL JUDGE-READY CLOSEOUT" | Add-Content $log
"NO SOURCE WRITE / NO MIGRATION / NO DB WRITE" | Add-Content $log
"============================================================" | Add-Content $log

function Section($name) {
  Write-Host ""
  Write-Host "[$name]"
  "" | Add-Content $log
  "============================================================" | Add-Content $log
  $name | Add-Content $log
  "============================================================" | Add-Content $log
}

Section "0. PREFLIGHT"
$pre=@'
from pathlib import Path

required = [
    "/app/app/services/track_b_smart_intake.py",
    "/app/app/services/track_b_smart_import.py",
    "/app/app/services/track_b_smart_spatial_import_plan.py",
    "/app/app/services/track_b_smart_transactional_site.py",
    "/app/app/services/track_b_smart_transactional_gis.py",
    "/app/app/services/track_b_smart_import_all.py",
]
for item in required:
    assert Path(item).exists(), item

track_b = Path("/app/app/api/v1/track_b.py").read_text()
for route in (
    "/organizer-intake/inspect",
    "/organizer-intake/prepare",
    "/organizer-intake/site-candidates",
    "/organizer-intake/site-resolution/upload",
    "/organizer-intake/import-plan",
    "/organizer-intake/import-all",
):
    assert route in track_b, route

print("smart_organizer_backend_contract=PASS")
'@
$preOut=$pre | docker compose exec -T -w /app backend python - 2>&1
$preOut | Tee-Object -FilePath $log -Append
if($LASTEXITCODE-ne 0){throw "Smart Organizer backend contract preflight failed."}

Section "1. FRONTEND CONTRACT"
$front=@'
const fs=require("fs");
const files={
  page:"/app/src/pages/TrackBWorkspacePage.tsx",
  comp:"/app/src/components/SmartOrganizerControlledImport.tsx",
  api:"/app/src/lib/api/trackB.ts"
};
for(const p of Object.values(files)){if(!fs.existsSync(p))throw new Error("missing "+p);}
const page=fs.readFileSync(files.page,"utf8");
const comp=fs.readFileSync(files.comp,"utf8");
const api=fs.readFileSync(files.api,"utf8");

for(const token of [
  "SMART_ORGANIZER_PHASE2D1_FRONTEND",
  "Analyze organizer package",
  "Confirm Site & build spatial import plan",
  "Review final Import All",
  "CONFIRM & IMPORT ALL"
]){
  if(!(page.includes(token)||comp.includes(token))) throw new Error("missing "+token);
}
for(const route of [
  "organizer-intake/site-candidates",
  "organizer-intake/site-resolution/upload",
  "organizer-intake/import-plan",
  "organizer-intake/import-all"
]){
  if(!api.includes(route)) throw new Error("missing "+route);
}
console.log("smart_organizer_frontend_contract=PASS");
'@
$frontOut=$front | docker compose exec -T -w /app frontend node - 2>&1
$frontOut | Tee-Object -FilePath $log -Append
if($LASTEXITCODE-ne 0){throw "Frontend contract failed."}

Section "2. FOCUSED SMART ORGANIZER REGRESSION"
$tests = @(
  "tests/test_track_b_smart_organizer_intake_v1.py",
  "tests/test_track_b_smart_organizer_zip_v1_2_2.py",
  "tests/test_track_b_smart_organizer_gis_bundle_v1_3.py",
  "tests/test_track_b_smart_organizer_format_coverage_v1_3_3.py",
  "tests/test_track_b_smart_import_phase2a.py",
  "tests/test_track_b_smart_site_discovery_phase2b2.py",
  "tests/test_track_b_smart_site_resolution_phase2b3.py",
  "tests/test_track_b_smart_transactional_site_phase2c1.py",
  "tests/test_track_b_smart_spatial_import_plan_phase2c2.py",
  "tests/test_track_b_smart_transactional_gis_phase2c3a.py",
  "tests/test_track_b_smart_import_all_phase2c3b.py"
)

$existing = @()
foreach($t in $tests){
  docker compose exec -T backend test -f "/app/$t" | Out-Null
  if($LASTEXITCODE-eq 0){$existing += $t}
}

if($existing.Count -eq 0){
  throw "No focused Smart Organizer tests found."
}

Write-Host "Focused tests found: $($existing.Count)"
"focused_test_files=$($existing.Count)" | Add-Content $log
$focusedOut = docker compose exec -T backend python -m pytest -q $existing 2>&1
$focusedOut | Tee-Object -FilePath $log -Append
if($LASTEXITCODE-ne 0){throw "Focused Smart Organizer regression failed."}

Section "3. FULL BACKEND REGRESSION"
$backendOut=docker compose exec -T backend python -m pytest -q 2>&1
$backendOut | Tee-Object -FilePath $log -Append
if($LASTEXITCODE-ne 0){throw "Full backend regression failed."}

Section "4. FRONTEND TYPECHECK"
$typeOut=docker compose exec -T frontend npm run typecheck 2>&1
$typeOut | Tee-Object -FilePath $log -Append
if($LASTEXITCODE-ne 0){throw "Frontend typecheck failed."}

Section "5. FRONTEND TESTS"
$testOut=docker compose exec -T frontend npm test 2>&1
$testOut | Tee-Object -FilePath $log -Append
if($LASTEXITCODE-ne 0){throw "Frontend tests failed."}

Section "6. FRONTEND PRODUCTION BUILD"
$buildOut=docker compose exec -T frontend npm run build 2>&1
$buildOut | Tee-Object -FilePath $log -Append
if($LASTEXITCODE-ne 0){throw "Frontend production build failed."}

Section "7. RUNTIME HEALTH"
$psOut=docker compose ps 2>&1
$psOut | Tee-Object -FilePath $log -Append
if($LASTEXITCODE-ne 0){throw "docker compose ps failed."}

$frontStatus=(Invoke-WebRequest -UseBasicParsing "http://localhost:5177" -TimeoutSec 20).StatusCode
"frontend_http_status=$frontStatus" | Tee-Object -FilePath $log -Append
if($frontStatus-ne 200){throw "Frontend HTTP is not 200."}

$backendStatus=(Invoke-WebRequest -UseBasicParsing "http://localhost:8007/health" -TimeoutSec 20).StatusCode
"backend_health_http_status=$backendStatus" | Tee-Object -FilePath $log -Append
if($backendStatus-ne 200){throw "Backend health HTTP is not 200."}

Section "8. FINAL DB PRESERVATION AUDIT"
$db=@'
from app.db import get_session_factory
from sqlalchemy import text

with get_session_factory()() as db:
    rev=db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    sites=db.execute(text("SELECT COUNT(*) FROM sites")).scalar()
    layers=db.execute(text("SELECT COUNT(*) FROM gis_layers")).scalar()
    features=db.execute(text("SELECT COUNT(*) FROM gis_features")).scalar()
    acceptance_sites=db.execute(text("""
        SELECT COUNT(*) FROM sites
        WHERE name LIKE 'PHASE2D2 GIS INTEGRATION ACCEPTANCE%'
           OR name LIKE 'PHASE2C3B COMMIT FIXTURE%'
           OR name='Competition Site'
    """)).scalar()
    print("alembic_revision=", rev)
    print("site_count=", sites)
    print("gis_layers=", layers)
    print("gis_features=", features)
    print("acceptance_fixture_site_count=", acceptance_sites)
    assert rev == "0020"
    assert sites == 2
    assert layers == 0
    assert features == 0
    assert acceptance_sites == 0
    print("db_preservation=PASS")
'@
$dbOut=$db | docker compose exec -T -w /app backend python - 2>&1
$dbOut | Tee-Object -FilePath $log -Append
if($LASTEXITCODE-ne 0){throw "Final DB preservation audit failed."}

Section "9. ACCEPTED CAPABILITY SUMMARY"
@"
Smart Organizer intake / ZIP / GIS bundle handling: ACCEPTED
Format coverage and GDAL conversion foundation: ACCEPTED
Competition Site discovery and confirmation: ACCEPTED
Spatial import planning: ACCEPTED
Transactional Site creation: ACCEPTED
Transactional GIS layer/feature persistence: ACCEPTED
Persistent Import All orchestration: ACCEPTED
Controlled commit / duplicate-reuse acceptance: ACCEPTED
Frontend controlled Import All workflow: ACCEPTED
Live frontend persistent Import All: ACCEPTED
Post-import native GIS read: ACCEPTED
Site applicability consumption: ACCEPTED
PostGIS site area analysis: ACCEPTED
PostGIS overlap analysis: ACCEPTED
Nearest-feature analysis: ACCEPTED
Acceptance fixture cleanup / DB baseline restoration: ACCEPTED

SMART ORGANIZER FINAL STATUS: CLOSED / JUDGE-READY
NEXT FOCUS: AI / PLANNING OFFICER CONSUMPTION + DEMO JUDGE FLOW
"@ | Tee-Object -FilePath $log -Append

Write-Host ""
Write-Host "============================================================"
Write-Host "SMART ORGANIZER FINAL JUDGE-READY CLOSEOUT PASS"
Write-Host "============================================================"
Write-Host "RESULT SAVED TO:"
Write-Host $log
