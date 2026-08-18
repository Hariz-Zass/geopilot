$ErrorActionPreference="Continue"

Write-Host "============================================================"
Write-Host "GeoPilot Phase 2C.3B Controlled Commit Acceptance V3"
Write-Host "Repair: GeoPackage Feature.id-safe verification"
Write-Host "REAL COMMIT -> VERIFY REUSE -> CLEANUP -> BASELINE RESTORE"
Write-Host "============================================================"

$root=(Get-Location).Path
$log=Join-Path $root "artifacts\phase_2c3b_controlled_commit_acceptance_FINAL_V3.txt"
$py=Join-Path $root "phase2c3b_controlled_commit_acceptance_v3.py"

if(-not(Test-Path $py)){
    throw "Required acceptance script missing: $py"
}

New-Item -ItemType Directory -Force (Join-Path $root "artifacts") | Out-Null

"============================================================" | Set-Content $log
"GeoPilot AI Track B - Phase 2C.3B FINAL V3" | Add-Content $log
"CONTROLLED COMMIT ACCEPTANCE" | Add-Content $log
"============================================================" | Add-Content $log
"Production source modification: NONE" | Add-Content $log
"Migration: NONE" | Add-Content $log
"Container restart/rebuild: NONE" | Add-Content $log
"Synthetic tiny fixture only: YES" | Add-Content $log
"V3 repair: DO NOT REQUIRE GeoPackage to preserve GeoJSON Feature.id" | Add-Content $log
"" | Add-Content $log

Write-Host "[0] App import preflight"
$pre=@'
from app.services.track_b_smart_import_all import ImportAllRequest, execute_persistent_import_all
from app.services.track_b_smart_transactional_gis import create_gis_layer_uncommitted, ingest_features_uncommitted
from app.services.track_b_smart_transactional_site import create_competition_site_uncommitted
print("APP_IMPORT_PREFLIGHT=PASS")
'@
$preOut = $pre | docker compose exec -T -w /app backend python - 2>&1
$preExit=$LASTEXITCODE
"============================================================" | Add-Content $log
"IMPORT PREFLIGHT" | Add-Content $log
"============================================================" | Add-Content $log
$preOut | Add-Content $log
"import_preflight_exit=$preExit" | Add-Content $log
"" | Add-Content $log
$preOut | ForEach-Object { Write-Host $_ }
if($preExit-ne 0){
    Write-Host "STOP: import preflight failed."
    Write-Host "RESULT SAVED TO: $log"
    exit 1
}

Write-Host "[1] Copy acceptance script into backend"
docker compose cp "$py" backend:/app/phase2c3b_controlled_commit_acceptance_v3.py | Out-Null
if($LASTEXITCODE-ne 0){
    "copy_acceptance_script=FAIL" | Add-Content $log
    Write-Host "STOP: failed to copy acceptance script."
    Write-Host "RESULT SAVED TO: $log"
    exit 1
}

Write-Host "[2] Run controlled commit acceptance"
$stdoutFile=Join-Path $root "artifacts\phase2c3b_v3_stdout.tmp"
$stderrFile=Join-Path $root "artifacts\phase2c3b_v3_stderr.tmp"
Remove-Item $stdoutFile,$stderrFile -ErrorAction SilentlyContinue

$p = Start-Process `
    -FilePath "docker" `
    -ArgumentList @("compose","exec","-T","-w","/app","backend","python","/app/phase2c3b_controlled_commit_acceptance_v3.py") `
    -Wait `
    -PassThru `
    -NoNewWindow `
    -RedirectStandardOutput $stdoutFile `
    -RedirectStandardError $stderrFile

$acceptExit=$p.ExitCode
$stdout=if(Test-Path $stdoutFile){Get-Content $stdoutFile -Raw}else{""}
$stderr=if(Test-Path $stderrFile){Get-Content $stderrFile -Raw}else{""}

"============================================================" | Add-Content $log
"ACCEPTANCE STDOUT" | Add-Content $log
"============================================================" | Add-Content $log
$stdout | Add-Content $log
"" | Add-Content $log
"============================================================" | Add-Content $log
"ACCEPTANCE STDERR" | Add-Content $log
"============================================================" | Add-Content $log
$stderr | Add-Content $log
"acceptance_process_started=True" | Add-Content $log
"acceptance_exit_code=$acceptExit" | Add-Content $log
"" | Add-Content $log

Write-Host $stdout
if($stderr){Write-Host $stderr}

Write-Host "[3] Independent final DB audit"
$audit=@'
from app.db import get_session_factory
from sqlalchemy import text
with get_session_factory()() as db:
    print("alembic_revision=",db.execute(text("SELECT version_num FROM alembic_version")).scalar())
    print("site_count=",db.execute(text("SELECT COUNT(*) FROM sites")).scalar())
    print("gis_layers=",db.execute(text("SELECT COUNT(*) FROM gis_layers")).scalar())
    print("gis_features=",db.execute(text("SELECT COUNT(*) FROM gis_features")).scalar())
    print("acceptance_sites=",db.execute(text("SELECT COUNT(*) FROM sites WHERE name LIKE 'PHASE2C3B COMMIT FIXTURE V3 %'")).scalar())
'@
$auditOut=$audit | docker compose exec -T -w /app backend python - 2>&1
$auditExit=$LASTEXITCODE

"============================================================" | Add-Content $log
"INDEPENDENT FINAL DB AUDIT" | Add-Content $log
"============================================================" | Add-Content $log
$auditOut | Add-Content $log
"audit_exit_code=$auditExit" | Add-Content $log
"" | Add-Content $log

$auditOut | ForEach-Object { Write-Host $_ }

Write-Host "[4] Focused regression"
$regOut=docker compose exec -T backend python -m pytest -q `
    tests/test_track_b_smart_import_all_phase2c3b.py `
    tests/test_track_b_smart_transactional_gis_phase2c3a.py `
    tests/test_track_b_smart_spatial_import_plan_phase2c2.py `
    tests/test_track_b_smart_transactional_site_phase2c1.py 2>&1
$regExit=$LASTEXITCODE

"============================================================" | Add-Content $log
"FOCUSED REGRESSION" | Add-Content $log
"============================================================" | Add-Content $log
$regOut | Add-Content $log
"regression_exit_code=$regExit" | Add-Content $log
"" | Add-Content $log

$regOut | ForEach-Object { Write-Host $_ }

$logText=Get-Content $log -Raw
$pythonPass=$logText.Contains("PHASE 2C.3B CONTROLLED COMMIT ACCEPTANCE: PASS")
$dbPass=(
    $logText -match "site_count=\s*2" -and
    $logText -match "gis_layers=\s*0" -and
    $logText -match "gis_features=\s*0" -and
    $logText -match "acceptance_sites=\s*0"
)

"============================================================" | Add-Content $log
"FINAL HOST GATE" | Add-Content $log
"============================================================" | Add-Content $log
"import_preflight_exit=$preExit" | Add-Content $log
"acceptance_exit_code=$acceptExit" | Add-Content $log
"audit_exit_code=$auditExit" | Add-Content $log
"regression_exit_code=$regExit" | Add-Content $log
"python_pass_marker=$pythonPass" | Add-Content $log
"db_baseline_pass=$dbPass" | Add-Content $log

Remove-Item $stdoutFile,$stderrFile -ErrorAction SilentlyContinue

if($preExit -eq 0 -and $acceptExit -eq 0 -and $auditExit -eq 0 -and $regExit -eq 0 -and $pythonPass -and $dbPass){
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "PHASE 2C.3B CONTROLLED COMMIT ACCEPTANCE FINAL V3 PASS"
    Write-Host "============================================================"
    Write-Host "RESULT SAVED TO:"
    Write-Host $log
    exit 0
}

Write-Host ""
Write-Host "============================================================"
Write-Host "PHASE 2C.3B CONTROLLED COMMIT ACCEPTANCE FINAL V3 BLOCKED"
Write-Host "============================================================"
Write-Host "Do not retry blindly. Send this file to ChatGPT:"
Write-Host $log
exit 1
