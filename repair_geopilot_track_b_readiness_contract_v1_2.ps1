$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Api="$Root\backend\app\api\v1\track_b.py"
$Schema="$Root\backend\app\schemas\track_b.py"
$Tests="$Root\backend\tests\test_track_b_hackathon.py"

foreach($P in @($Api,$Schema,$Tests)){
    if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Track B Readiness Contract Repair V1.2"
Write-Host "Robust fixture repair using function-scoped regex"
Write-Host "NO DB WRITE / NO MIGRATION / NO FRONTEND SOURCE CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\track_b_readiness_contract_repair_v1_2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Api "$Backup\track_b_api.py"
Copy-Item $Schema "$Backup\track_b_schema.py"
Copy-Item $Tests "$Backup\test_track_b_hackathon.py"
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Confirm rollback state"
    $apiText=Get-Content $Api -Raw
    $schemaText=Get-Content $Schema -Raw
    if($apiText -notmatch '"competition_mode": True'){ throw "Expected rollback API state not found." }
    if($schemaText -notmatch 'competition_mode:\s*bool'){ throw "Expected rollback schema state not found." }
    Write-Host "rollback_state=CONFIRMED"

    Write-Host "[1] Repair capabilities response"
    $apiText=$apiText.Replace('"competition_mode": True,','"evidence_architecture": "provenance_controlled",')
    $apiText=$apiText.Replace('"evidence_policy": "organizer_supplied_only",','"evidence_policy": "provenance_controlled",')
    Set-Content $Api $apiText -Encoding UTF8

    Write-Host "[2] Repair readiness response schema"
    $schemaText=Get-Content $Schema -Raw
    $schemaText=[regex]::Replace($schemaText,'(?m)^\s{4}competition_mode:\s*bool\s*\r?\n','')
    $schemaText=$schemaText.Replace(
        '    evidence_policy: str = "organizer_supplied_only"',
        '    evidence_architecture: str = "provenance_controlled"' + "`r`n" +
        '    evidence_policy: str = "provenance_controlled"'
    )
    $schemaText=$schemaText.Replace('    organizer_dataset_count: int','    eligible_dataset_count: int')
    Set-Content $Schema $schemaText -Encoding UTF8

    Write-Host "[3] Robustly repair pair-selector test fixtures"
    $py = @'
from pathlib import Path
import re

path = Path("/app/tests/test_track_b_hackathon.py")
text = path.read_text(encoding="utf-8-sig")

targets = [
    (
        "test_track_b_hackathon_pair_selector_requires_same_site_and_stage",
        'checksum_sha256="a" * 64, source_uri="file:///tmp/test-track-b.tif",',
    ),
    (
        "test_track_b_pair_selector_rejects_synthetic_fixture",
        'checksum_sha256="b" * 64, source_uri="file:///tmp/test-track-b-synthetic.tif",',
    ),
]

for fn_name, insertion in targets:
    start = text.find(f"def {fn_name}(")
    if start < 0:
        raise SystemExit(f"FUNCTION_NOT_FOUND:{fn_name}")
    next_def = text.find("\ndef ", start + 1)
    end = len(text) if next_def < 0 else next_def
    block = text[start:end]

    if "checksum_sha256=" in block and "source_uri=" in block:
        print(f"{fn_name}: already repaired")
        continue

    # Insert immediately after the acquisition_datetime assignment line.
    pattern = r'(?m)^(\s*acquisition_datetime\s*=.*,\s*)$'
    m = re.search(pattern, block)
    if not m:
        # Fixture uses acquisition_datetime as a keyword argument on an existing line.
        pattern = r'(?m)^(\s*id=.*acquisition_datetime=.*,\s*)$'
        m = re.search(pattern, block)
    if not m:
        raise SystemExit(f"ACQUISITION_DATETIME_LINE_NOT_FOUND:{fn_name}")

    indent = re.match(r'^(\s*)', m.group(1)).group(1)
    replacement = m.group(1) + "\n" + indent + insertion
    block = block[:m.start()] + replacement + block[m.end():]
    text = text[:start] + block + text[end:]
    print(f"{fn_name}: repaired")

path.write_text(text, encoding="utf-8")
print("TEST_FIXTURE_REPAIR=PASS")
'@
    $Temp="$Root\backend\_repair_track_b_test_fixtures_v1_2.py"
    Set-Content $Temp $py -Encoding UTF8
    try {
        docker compose exec -T backend python /app/_repair_track_b_test_fixtures_v1_2.py
        if($LASTEXITCODE-ne 0){ throw "Robust fixture repair failed." }
    }
    finally {
        Remove-Item $Temp -Force -ErrorAction SilentlyContinue
    }

    Write-Host "[4] Contract source verification"
    $joined=(Get-Content $Api -Raw)+"`n"+(Get-Content $Schema -Raw)
    foreach($legacy in @(
        '"competition_mode": True',
        '"evidence_policy": "organizer_supplied_only"',
        'competition_mode: bool',
        'organizer_dataset_count: int'
    )){
        if($joined -match [regex]::Escape($legacy)){ throw "Legacy contract marker remains: $legacy" }
    }
    foreach($required in @('evidence_architecture','provenance_controlled','eligible_dataset_count')){
        if($joined -notmatch [regex]::Escape($required)){ throw "Expected new contract marker missing: $required" }
    }
    Write-Host "contract_source=PASS"

    Write-Host "[5] Test fixture verification"
    $testText=Get-Content $Tests -Raw
    if($testText -notmatch 'test_track_b_hackathon_pair_selector_requires_same_site_and_stage'){ throw "Target test missing." }
    if($testText -notmatch 'checksum_sha256="a" \* 64'){ throw "First fixture repair missing." }
    if($testText -notmatch 'checksum_sha256="b" \* 64'){ throw "Second fixture repair missing." }
    if($testText -notmatch 'source_uri="file:///tmp/test-track-b\.tif"'){ throw "First source URI repair missing." }
    if($testText -notmatch 'source_uri="file:///tmp/test-track-b-synthetic\.tif"'){ throw "Second source URI repair missing." }
    Write-Host "test_fixtures=PASS"

    Write-Host "[6] Syntax checks"
    docker compose exec -T backend python -m py_compile app/api/v1/track_b.py app/schemas/track_b.py tests/test_track_b_hackathon.py
    if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

    Write-Host "[7] Readiness schema verification"
    docker compose exec -T backend python -c "from app.schemas.track_b import TrackBReadinessResponse; f=TrackBReadinessResponse.model_fields; assert 'competition_mode' not in f; assert 'organizer_dataset_count' not in f; assert 'evidence_architecture' in f; assert 'eligible_dataset_count' in f; print('readiness_schema=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Schema verification failed." }

    Write-Host "[8] Track B hackathon regression"
    docker compose exec -T backend python -m pytest -q tests/test_track_b_hackathon.py
    if($LASTEXITCODE-ne 0){ throw "Track B hackathon regression failed." }

    Write-Host "[9] Track B acceptance regression"
    if(Test-Path "$Root\backend\tests\test_track_b_acceptance.py"){
        docker compose exec -T backend python -m pytest -q tests/test_track_b_acceptance.py
        if($LASTEXITCODE-ne 0){ throw "Track B acceptance regression failed." }
    }

    Write-Host "[10] Controlled Evidence architecture regression"
    if(Test-Path "$Root\backend\tests\test_controlled_evidence_architecture_v2_1.py"){
        docker compose exec -T backend python -m pytest -q tests/test_controlled_evidence_architecture_v2_1.py
        if($LASTEXITCODE-ne 0){ throw "Controlled Evidence architecture regression failed." }
    }

    Write-Host "[11] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[12] Backend health"
    docker compose ps backend

    Write-Host "[13] Runtime response schema"
    docker compose exec -T backend python -c "from app.schemas.track_b import TrackBReadinessResponse; print('runtime_fields=', sorted(TrackBReadinessResponse.model_fields))"
    if($LASTEXITCODE-ne 0){ throw "Runtime schema verification failed." }

    Write-Host "============================================================"
    Write-Host "TRACK B READINESS CONTRACT REPAIR V1.2 PASS"
    Write-Host "============================================================"
    Write-Host "Readiness legacy contract fields: REMOVED"
    Write-Host "Capabilities legacy competition fields: REMOVED"
    Write-Host "evidence_architecture: provenance_controlled"
    Write-Host "eligible_dataset_count: ENABLED"
    Write-Host "Pair-selector fixture repair: PASS"
    Write-Host "Production provenance selector: UNCHANGED"
    Write-Host "Closed Evidence architecture: NOT RESTORED"
    Write-Host "DB write: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend source change: NONE"
    Write-Host "Next gate: REFRESH UI + TRACK B READINESS LOAD"
    Write-Host "============================================================"
}
catch {
    Write-Host "REPAIR FAILED - restoring API/schema/tests backup."
    Copy-Item "$Backup\track_b_api.py" $Api -Force
    Copy-Item "$Backup\track_b_schema.py" $Schema -Force
    Copy-Item "$Backup\test_track_b_hackathon.py" $Tests -Force
    throw
}
