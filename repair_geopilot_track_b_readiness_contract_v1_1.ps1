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
Write-Host "GeoPilot Track B Readiness Contract Repair V1.1"
Write-Host "Contract repair + stale Track B test-fixture repair"
Write-Host "NO DB WRITE / NO MIGRATION / NO FRONTEND SOURCE CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\track_b_readiness_contract_repair_v1_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Api "$Backup\track_b_api.py"
Copy-Item $Schema "$Backup\track_b_schema.py"
Copy-Item $Tests "$Backup\test_track_b_hackathon.py"
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Confirm V1 rollback + V2.1 production architecture"
    $apiText=Get-Content $Api -Raw
    $schemaText=Get-Content $Schema -Raw
    $testText=Get-Content $Tests -Raw
    $workflowText=Get-Content "$Root\backend\app\services\track_b_workflow.py" -Raw

    if($apiText -notmatch '"competition_mode": True'){ throw "Expected V1 rollback state not found in API." }
    if($schemaText -notmatch 'competition_mode:\s*bool'){ throw "Expected V1 rollback state not found in schema." }
    if($workflowText -notmatch 'checksum_sha256'){ throw "Expected V2.1 provenance selector not found." }
    Write-Host "state=CONFIRMED"

    Write-Host "[1] Repair capabilities response contract"
    $apiText=$apiText.Replace('"competition_mode": True,','"evidence_architecture": "provenance_controlled",')
    $apiText=$apiText.Replace('"evidence_policy": "organizer_supplied_only",','"evidence_policy": "provenance_controlled",')
    Set-Content -Path $Api -Value $apiText -Encoding UTF8

    Write-Host "[2] Repair readiness response schema"
    $schemaText=Get-Content $Schema -Raw
    $schemaText=[regex]::Replace($schemaText,'(?m)^\s{4}competition_mode:\s*bool\s*\r?\n','')
    $schemaText=$schemaText.Replace(
        '    evidence_policy: str = "organizer_supplied_only"',
        '    evidence_architecture: str = "provenance_controlled"' + "`r`n" +
        '    evidence_policy: str = "provenance_controlled"'
    )
    $schemaText=$schemaText.Replace(
        '    organizer_dataset_count: int',
        '    eligible_dataset_count: int'
    )
    Set-Content -Path $Schema -Value $schemaText -Encoding UTF8

    Write-Host "[3] Repair stale Track B test fixtures only"
    $testText=Get-Content $Tests -Raw

    $old1='id=uuid.uuid4(), site_id=site_id, created_at=now, acquisition_datetime="2026-01-01T00:00:00Z",'
    $new1='id=uuid.uuid4(), site_id=site_id, created_at=now, acquisition_datetime="2026-01-01T00:00:00Z",' + "`r`n" +
          '                checksum_sha256="a" * 64, source_uri="file:///tmp/test-track-b.tif",'
    if($testText.Contains($old1)){
        $testText=$testText.Replace($old1,$new1)
    } else {
        throw "First stale pair-selector fixture pattern not found."
    }

    $old2='id=uuid.uuid4(), site_id=site, created_at=now,' + "`r`n" +
          '                acquisition_datetime="2026-01-01T00:00:00Z" if role == "before" else "2026-06-01T00:00:00Z",'
    if(-not $testText.Contains($old2)){
        $old2='id=uuid.uuid4(), site_id=site, created_at=now,' + "`n" +
              '                acquisition_datetime="2026-01-01T00:00:00Z" if role == "before" else "2026-06-01T00:00:00Z",'
    }
    $new2='id=uuid.uuid4(), site_id=site, created_at=now,' + "`r`n" +
          '                acquisition_datetime="2026-01-01T00:00:00Z" if role == "before" else "2026-06-01T00:00:00Z",' + "`r`n" +
          '                checksum_sha256="b" * 64, source_uri="file:///tmp/test-track-b-synthetic.tif",'
    if($testText.Contains($old2)){
        $testText=$testText.Replace($old2,$new2)
    } else {
        throw "Second stale pair-selector fixture pattern not found."
    }

    Set-Content -Path $Tests -Value $testText -Encoding UTF8

    Write-Host "[4] Source verification"
    $joined=(Get-Content $Api -Raw) + "`n" + (Get-Content $Schema -Raw)
    foreach($legacy in @(
        '"competition_mode": True',
        '"evidence_policy": "organizer_supplied_only"',
        'competition_mode: bool',
        'organizer_dataset_count: int'
    )){
        if($joined -match [regex]::Escape($legacy)){ throw "Legacy readiness contract remains: $legacy" }
    }
    foreach($required in @(
        'evidence_architecture',
        'provenance_controlled',
        'eligible_dataset_count'
    )){
        if($joined -notmatch [regex]::Escape($required)){ throw "New readiness contract missing: $required" }
    }

    $testText=Get-Content $Tests -Raw
    if($testText -notmatch 'checksum_sha256="a" \* 64'){ throw "First fixture repair missing." }
    if($testText -notmatch 'checksum_sha256="b" \* 64'){ throw "Second fixture repair missing." }
    Write-Host "contract_source=PASS"
    Write-Host "test_fixture_repair=PASS"

    Write-Host "[5] Syntax checks"
    docker compose exec -T backend python -m py_compile app/api/v1/track_b.py app/schemas/track_b.py tests/test_track_b_hackathon.py
    if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

    Write-Host "[6] Focused readiness schema verification"
    docker compose exec -T backend python -c "from app.schemas.track_b import TrackBReadinessResponse; f=TrackBReadinessResponse.model_fields; assert 'competition_mode' not in f; assert 'organizer_dataset_count' not in f; assert 'evidence_architecture' in f; assert 'eligible_dataset_count' in f; print('readiness_schema=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Readiness schema verification failed." }

    Write-Host "[7] Track B hackathon regression"
    docker compose exec -T backend python -m pytest -q tests/test_track_b_hackathon.py
    if($LASTEXITCODE-ne 0){ throw "Track B hackathon regression failed." }

    Write-Host "[8] Track B acceptance regression"
    if(Test-Path "$Root\backend\tests\test_track_b_acceptance.py"){
        docker compose exec -T backend python -m pytest -q tests/test_track_b_acceptance.py
        if($LASTEXITCODE-ne 0){ throw "Track B acceptance regression failed." }
    }

    Write-Host "[9] Controlled Evidence V2.1 architecture regression"
    if(Test-Path "$Root\backend\tests\test_controlled_evidence_architecture_v2_1.py"){
        docker compose exec -T backend python -m pytest -q tests/test_controlled_evidence_architecture_v2_1.py
        if($LASTEXITCODE-ne 0){ throw "Controlled Evidence architecture regression failed." }
    }

    Write-Host "[10] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[11] Backend health"
    docker compose ps backend

    Write-Host "[12] Runtime readiness schema import"
    docker compose exec -T backend python -c "from app.schemas.track_b import TrackBReadinessResponse; print('runtime_fields=',sorted(TrackBReadinessResponse.model_fields))"
    if($LASTEXITCODE-ne 0){ throw "Runtime schema import failed." }

    Write-Host "============================================================"
    Write-Host "TRACK B READINESS CONTRACT REPAIR V1.1 PASS"
    Write-Host "============================================================"
    Write-Host "Response schema legacy competition fields: REMOVED"
    Write-Host "Capabilities legacy competition fields: REMOVED"
    Write-Host "evidence_architecture: provenance_controlled"
    Write-Host "eligible_dataset_count: ENABLED"
    Write-Host "Stale Track B pair-selector test fixtures: REPAIRED"
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
