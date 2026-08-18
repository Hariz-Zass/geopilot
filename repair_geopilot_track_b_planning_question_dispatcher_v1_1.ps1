$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Api="$Root\backend\app\api\v1\track_b.py"
$Test="$Root\backend\tests\test_track_b_planning_question_dispatcher_manifest_v1_1.py"

if(!(Test-Path $Api)){ throw "Missing required file: $Api" }

Write-Host "============================================================"
Write-Host "GeoPilot Track B Planning Question Dispatcher V1.1"
Write-Host "Repair undefined analysis-manifest lookup"
Write-Host "NO DB WRITE / NO MIGRATION / NO FRONTEND SOURCE CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\track_b_planning_question_dispatcher_v1_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Api "$Backup\track_b_api.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_track_b_planning_question_dispatcher_manifest_v1_1.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Preflight undefined-call gate"
    $t=Get-Content $Api -Raw
    if($t -notmatch 'get_track_b_analysis_manifest'){ throw "Expected undefined manifest call not found." }
    if($t -notmatch 'artifact_path'){ throw "Existing artifact_path import/use not found." }
    Write-Host "undefined_manifest_call=CONFIRMED"

    Write-Host "[1] Add json import if required"
    if($t -notmatch '(?m)^import json\s*$'){
        $t=$t.Replace("import uuid`r`n","import json`r`nimport uuid`r`n")
        if($t -notmatch '(?m)^import json\s*$'){
            $t=$t.Replace("import uuid`n","import json`nimport uuid`n")
        }
    }

    Write-Host "[2] Replace undefined helper with existing analysis.json artifact path"
    $old=@'
            analysis = get_track_b_analysis_manifest(
                project_id=project_id,
                analysis_id=analysis_id,
            )
'@
    $new=@'
            manifest_path = artifact_path(
                project_id,
                analysis_id,
                "analysis.json",
            )
            if not manifest_path.is_file():
                raise TrackBAIError(
                    "Track B analysis manifest is not available for planning-document research."
                )
            analysis = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
'@

    if($t.Contains($old)){
        $t=$t.Replace($old,$new)
    } else {
        $pattern='(?ms)\s{12}analysis = get_track_b_analysis_manifest\(\s*project_id=project_id,\s*analysis_id=analysis_id,\s*\)\s*'
        if(-not [regex]::IsMatch($t,$pattern)){ throw "Manifest call block not found safely." }
        $t=[regex]::Replace($t,$pattern,"`r`n$new",1)
    }
    Set-Content $Api $t -Encoding UTF8

    Write-Host "[3] Install focused regression"
    $testText=@'
from pathlib import Path


def test_dispatcher_manifest_lookup_uses_existing_artifact_path():
    text = Path("app/api/v1/track_b.py").read_text(encoding="utf-8-sig")
    assert "get_track_b_analysis_manifest" not in text
    assert 'artifact_path(' in text
    assert '"analysis.json"' in text
    assert "json.loads" in text
    assert "TRACKB_PLANNING_QUESTION_DISPATCHER_V1" in text
'@
    Set-Content $Test $testText -Encoding UTF8

    Write-Host "[4] Syntax checks"
    docker compose exec -T backend python -m py_compile app/api/v1/track_b.py tests/test_track_b_planning_question_dispatcher_manifest_v1_1.py
    if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

    Write-Host "[5] Focused manifest regression"
    docker compose exec -T backend python -m pytest -q tests/test_track_b_planning_question_dispatcher_manifest_v1_1.py
    if($LASTEXITCODE-ne 0){ throw "Manifest regression failed." }

    Write-Host "[6] Preserve dispatcher V1 regression"
    if(Test-Path "$Root\backend\tests\test_track_b_planning_question_dispatcher_v1.py"){
        docker compose exec -T backend python -m pytest -q tests/test_track_b_planning_question_dispatcher_v1.py
        if($LASTEXITCODE-ne 0){ throw "Dispatcher V1 regression failed." }
    }

    Write-Host "[7] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[8] Backend health"
    docker compose ps backend

    Write-Host "[9] Runtime import verification"
    docker compose exec -T backend python -c "import app.api.v1.track_b as m; assert hasattr(m,'planner_decision_workspace'); print('track_b_api_import=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Runtime import verification failed." }

    Write-Host "============================================================"
    Write-Host "TRACK B PLANNING QUESTION DISPATCHER V1.1 PASS"
    Write-Host "============================================================"
    Write-Host "Undefined get_track_b_analysis_manifest call: REMOVED"
    Write-Host "Analysis manifest lookup: existing artifact_path(..., analysis.json)"
    Write-Host "Dispatcher architecture: PRESERVED"
    Write-Host "Planning Orchestrator route: PRESERVED"
    Write-Host "Auto Research RT/RSN/RKK/GPP: PRESERVED"
    Write-Host "DB write in repair: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend source change: NONE"
    Write-Host "Next gate: RETEST LIVE GPP QUESTION"
    Write-Host "============================================================"
}
catch {
    Write-Host "REPAIR FAILED - restoring API/test backup."
    Copy-Item "$Backup\track_b_api.py" $Api -Force
    if(Test-Path "$Backup\test_track_b_planning_question_dispatcher_manifest_v1_1.py"){
        Copy-Item "$Backup\test_track_b_planning_question_dispatcher_manifest_v1_1.py" $Test -Force
    } else {
        Remove-Item $Test -Force -ErrorAction SilentlyContinue
    }
    throw
}
