$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Api="$Root\backend\app\api\v1\track_b.py"
$Test="$Root\backend\tests\test_track_b_planning_question_dispatcher_manifest_v1_2.py"

if(!(Test-Path $Api)){ throw "Missing required file: $Api" }

Write-Host "============================================================"
Write-Host "GeoPilot Track B Planning Question Dispatcher V1.2"
Write-Host "Exact-line repair for analysis manifest lookup"
Write-Host "NO DB WRITE / NO MIGRATION / NO FRONTEND SOURCE CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\track_b_planning_question_dispatcher_v1_2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Api "$Backup\track_b_api.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_track_b_planning_question_dispatcher_manifest_v1_2.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Preflight exact source gate"
    $t=Get-Content $Api -Raw

    $oldLine='            analysis = get_track_b_analysis_manifest(project_id=project_id, analysis_id=analysis_id)'
    if(-not $t.Contains($oldLine)){
        throw "Exact undefined manifest call line not found."
    }
    Write-Host "exact_undefined_call=CONFIRMED"

    Write-Host "[1] Add json import if missing"
    if($t -notmatch '(?m)^import json\s*$'){
        if($t.Contains("import uuid`r`n")){
            $t=$t.Replace("import uuid`r`n","import json`r`nimport uuid`r`n")
        } elseif($t.Contains("import uuid`n")){
            $t=$t.Replace("import uuid`n","import json`nimport uuid`n")
        } else {
            throw "import uuid anchor not found."
        }
    }

    Write-Host "[2] Replace exact undefined manifest call"
    $newBlock=@'
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

    $t=$t.Replace($oldLine,$newBlock.TrimEnd())
    Set-Content $Api $t -Encoding UTF8

    Write-Host "[3] Static source verification"
    $t=Get-Content $Api -Raw
    if($t -match 'get_track_b_analysis_manifest'){ throw "Undefined manifest helper remains." }
    foreach($required in @(
        'import json',
        'artifact_path(',
        '"analysis.json"',
        'json.loads(',
        'TRACKB_PLANNING_QUESTION_DISPATCHER_V1',
        '"documents.search" in route.tools'
    )){
        if($t -notmatch [regex]::Escape($required)){ throw "Required marker missing: $required" }
    }
    Write-Host "source_repair=PASS"

    Write-Host "[4] Install focused regression test"
    $testText=@'
from pathlib import Path


def test_dispatcher_manifest_lookup_uses_existing_analysis_artifact():
    text = Path("app/api/v1/track_b.py").read_text(encoding="utf-8-sig")
    assert "get_track_b_analysis_manifest" not in text
    assert "import json" in text
    assert 'artifact_path(' in text
    assert '"analysis.json"' in text
    assert "json.loads(" in text
    assert "TRACKB_PLANNING_QUESTION_DISPATCHER_V1" in text
    assert '"documents.search" in route.tools' in text
'@
    Set-Content $Test $testText -Encoding UTF8

    Write-Host "[5] Syntax checks"
    docker compose exec -T backend python -m py_compile app/api/v1/track_b.py tests/test_track_b_planning_question_dispatcher_manifest_v1_2.py
    if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

    Write-Host "[6] Focused manifest regression"
    docker compose exec -T backend python -m pytest -q tests/test_track_b_planning_question_dispatcher_manifest_v1_2.py
    if($LASTEXITCODE-ne 0){ throw "Manifest regression failed." }

    Write-Host "[7] Preserve Dispatcher V1 regression"
    if(Test-Path "$Root\backend\tests\test_track_b_planning_question_dispatcher_v1.py"){
        docker compose exec -T backend python -m pytest -q tests/test_track_b_planning_question_dispatcher_v1.py
        if($LASTEXITCODE-ne 0){ throw "Dispatcher V1 regression failed." }
    }

    Write-Host "[8] Preserve Track B API import"
    docker compose exec -T backend python -c "import app.api.v1.track_b as m; assert hasattr(m,'planner_decision_workspace'); print('track_b_api_import=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Track B API import failed." }

    Write-Host "[9] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[10] Backend health"
    docker compose ps backend

    Write-Host "[11] Runtime import verification"
    docker compose exec -T backend python -c "import app.api.v1.track_b as m; print('runtime_dispatcher_import=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Runtime import verification failed." }

    Write-Host "============================================================"
    Write-Host "TRACK B PLANNING QUESTION DISPATCHER V1.2 PASS"
    Write-Host "============================================================"
    Write-Host "Undefined manifest helper: REMOVED"
    Write-Host "Manifest lookup: artifact_path(..., analysis.json)"
    Write-Host "Planning Orchestrator document route: PRESERVED"
    Write-Host "Terrain route: PRESERVED"
    Write-Host "Temporal Track B route: PRESERVED"
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

    if(Test-Path "$Backup\test_track_b_planning_question_dispatcher_manifest_v1_2.py"){
        Copy-Item "$Backup\test_track_b_planning_question_dispatcher_manifest_v1_2.py" $Test -Force
    } else {
        Remove-Item $Test -Force -ErrorAction SilentlyContinue
    }
    throw
}
