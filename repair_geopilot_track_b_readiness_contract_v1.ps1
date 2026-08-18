$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Api="$Root\backend\app\api\v1\track_b.py"
$Schema="$Root\backend\app\schemas\track_b.py"

foreach($P in @($Api,$Schema)){
    if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Track B Readiness Contract Repair V1"
Write-Host "Repair stale competition response contract after V2.1"
Write-Host "NO DB WRITE / NO MIGRATION / NO FRONTEND SOURCE CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\track_b_readiness_contract_repair_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Api "$Backup\track_b.py"
Copy-Item $Schema "$Backup\track_b_schema.py"
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[1] Preflight stale-contract gate"
    $apiText=Get-Content $Api -Raw
    $schemaText=Get-Content $Schema -Raw

    if($apiText -notmatch '"competition_mode": True'){ throw "Expected stale capabilities competition_mode field not found." }
    if($apiText -notmatch '"evidence_policy": "organizer_supplied_only"'){ throw "Expected stale capabilities evidence_policy not found." }
    if($schemaText -notmatch 'competition_mode:\s*bool'){ throw "Expected stale readiness competition_mode field not found." }
    if($schemaText -notmatch 'organizer_dataset_count:\s*int'){ throw "Expected stale readiness organizer_dataset_count field not found." }
    Write-Host "stale_contract=CONFIRMED"

    Write-Host "[2] Repair capabilities response"
    $apiText=$apiText.Replace('"competition_mode": True,','"evidence_architecture": "provenance_controlled",')
    $apiText=$apiText.Replace('"evidence_policy": "organizer_supplied_only",','"evidence_policy": "provenance_controlled",')
    Set-Content -Path $Api -Value $apiText -Encoding UTF8

    Write-Host "[3] Repair readiness response schema"
    $schemaText=$schemaText.Replace('    competition_mode: bool' + "`r`n",'')
    $schemaText=$schemaText.Replace('    competition_mode: bool' + "`n",'')
    $schemaText=$schemaText.Replace('    evidence_policy: str = "organizer_supplied_only"','    evidence_architecture: str = "provenance_controlled"' + "`r`n" + '    evidence_policy: str = "provenance_controlled"')
    $schemaText=$schemaText.Replace('    organizer_dataset_count: int','    eligible_dataset_count: int')
    Set-Content -Path $Schema -Value $schemaText -Encoding UTF8

    Write-Host "[4] Source contract verification"
    $apiText=Get-Content $Api -Raw
    $schemaText=Get-Content $Schema -Raw

    foreach($needle in @(
        '"competition_mode": True',
        '"evidence_policy": "organizer_supplied_only"',
        'competition_mode: bool',
        'organizer_dataset_count: int'
    )){
        if(($apiText + "`n" + $schemaText) -match [regex]::Escape($needle)){
            throw "Legacy contract marker remains: $needle"
        }
    }

    foreach($needle in @(
        'evidence_architecture',
        'provenance_controlled',
        'eligible_dataset_count'
    )){
        if(($apiText + "`n" + $schemaText) -notmatch [regex]::Escape($needle)){
            throw "Expected new contract marker missing: $needle"
        }
    }

    Write-Host "[5] Backend syntax check"
    docker compose exec -T backend python -m py_compile app/api/v1/track_b.py app/schemas/track_b.py
    if($LASTEXITCODE-ne 0){ throw "Backend syntax check failed." }

    Write-Host "[6] Focused schema import verification"
    docker compose exec -T backend python -c "from app.schemas.track_b import TrackBReadinessResponse; f=TrackBReadinessResponse.model_fields; assert 'competition_mode' not in f; assert 'organizer_dataset_count' not in f; assert 'evidence_architecture' in f; assert 'eligible_dataset_count' in f; print('readiness_schema=PASS'); print('fields=', sorted(f))"
    if($LASTEXITCODE-ne 0){ throw "Schema import verification failed." }

    Write-Host "[7] Track B tests"
    foreach($T in @(
        "tests/test_track_b_acceptance.py",
        "tests/test_track_b_hackathon.py"
    )){
        if(Test-Path "$Root\backend\$T"){
            docker compose exec -T backend python -m pytest -q $T
            if($LASTEXITCODE-ne 0){ throw "Track B regression failed: $T" }
        }
    }

    Write-Host "[8] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[9] Backend health"
    docker compose ps backend

    Write-Host "[10] Recent backend validation errors"
    docker compose logs --tail=80 backend | Select-String -Pattern "ResponseValidationError|competition_mode|organizer_dataset_count" -SimpleMatch

    Write-Host "============================================================"
    Write-Host "TRACK B READINESS CONTRACT REPAIR V1 PASS"
    Write-Host "============================================================"
    Write-Host "Capabilities competition_mode field: REMOVED"
    Write-Host "Capabilities evidence_policy: provenance_controlled"
    Write-Host "Readiness competition_mode field: REMOVED"
    Write-Host "Readiness organizer_dataset_count field: REMOVED"
    Write-Host "Readiness evidence_architecture field: ADDED"
    Write-Host "Readiness eligible_dataset_count field: ADDED"
    Write-Host "Closed Evidence architecture: NOT RESTORED"
    Write-Host "Frontend source change: NONE"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Next gate: REFRESH UI + READINESS LOAD"
    Write-Host "============================================================"
}
catch {
    Write-Host "REPAIR FAILED - restoring backup."
    Copy-Item "$Backup\track_b.py" $Api -Force
    Copy-Item "$Backup\track_b_schema.py" $Schema -Force
    throw
}
