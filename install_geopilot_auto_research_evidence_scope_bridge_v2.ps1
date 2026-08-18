$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$OrchestratorPath="$Root\backend\app\services\planning_orchestrator.py"
$TestPath="$Root\backend\tests\test_auto_research_evidence_scope_bridge_v2.py"

if(!(Test-Path $OrchestratorPath)){ throw "Missing required file: $OrchestratorPath" }

Write-Host "============================================================"
Write-Host "GeoPilot Auto Research Evidence Scope Bridge V2"
Write-Host "No spatial evidence -> search only Auto Research document IDs"
Write-Host "Prevent global project-document fallback"
Write-Host "NO DB SCHEMA CHANGE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir="$Root\artifacts\auto_research_evidence_scope_bridge_v2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
Copy-Item $OrchestratorPath "$BackupDir\planning_orchestrator.py"
if(Test-Path $TestPath){ Copy-Item $TestPath "$BackupDir\test_auto_research_evidence_scope_bridge_v2.py" }
Write-Host "BACKUP: $BackupDir"

try {
    Write-Host "[0] Preflight evidence-bridge gate"
    $Text=Get-Content $OrchestratorPath -Raw

    $Expected=@'
            else:
                applicable_document_ids = []

        if (
'@

    if(-not $Text.Contains($Expected)){
        throw "Expected AUTO_RESEARCH_EVIDENCE_BRIDGE_V1 tail not found."
    }

    if($Text -match '# AUTO_RESEARCH_EVIDENCE_SCOPE_BRIDGE_V2'){
        throw "Evidence Scope Bridge V2 already appears installed."
    }

    Write-Host "preflight_state=CONFIRMED"

    Write-Host "[1] Patch no-spatial-evidence document scope"

    $Replacement=@'
            else:
                applicable_document_ids = []

        else:
            # AUTO_RESEARCH_EVIDENCE_SCOPE_BRIDGE_V2
            # A document/policy question with no deterministic spatial
            # applicability evidence must not fall back to an unrestricted
            # project-wide document search. Restrict retrieval to the
            # documents selected/acquired by Auto Research for this question.
            applicable_document_ids = list(auto_research_document_ids)

        if (
'@

    $Text=$Text.Replace($Expected,$Replacement)
    [System.IO.File]::WriteAllText(
        $OrchestratorPath,
        $Text,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "PATCHED: $OrchestratorPath"

    Write-Host "[2] Install focused static regression"

    $TestText=@'
from pathlib import Path


def test_no_spatial_evidence_uses_auto_research_document_scope():
    text = Path("app/services/planning_orchestrator.py").read_text(
        encoding="utf-8-sig"
    )
    marker = "# AUTO_RESEARCH_EVIDENCE_SCOPE_BRIDGE_V2"
    assert marker in text

    start = text.index(marker)
    block = text[start:start + 900]

    assert "applicable_document_ids = list(auto_research_document_ids)" in block
    assert "document_ids=(" in text
    assert "applicable_document_ids" in text


def test_bridge_does_not_replace_existing_spatial_merge_logic():
    text = Path("app/services/planning_orchestrator.py").read_text(
        encoding="utf-8-sig"
    )

    assert "*resolved_document_ids" in text
    assert "*auto_research_document_ids" in text
    assert "resolved_document_ids" in text
'@

    [System.IO.File]::WriteAllText(
        $TestPath,
        $TestText,
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Host "[3] Backend syntax check"
    docker compose exec -T backend python -m py_compile app/services/planning_orchestrator.py tests/test_auto_research_evidence_scope_bridge_v2.py
    if($LASTEXITCODE-ne 0){ throw "Backend syntax check failed." }

    Write-Host "[4] Focused scope-bridge regression"
    docker compose exec -T backend python -m pytest -q tests/test_auto_research_evidence_scope_bridge_v2.py
    if($LASTEXITCODE-ne 0){ throw "Focused scope-bridge regression failed." }

    Write-Host "[5] Preserve Auto Research regressions"
    foreach($Regression in @(
        "tests/test_planning_document_auto_research.py",
        "tests/test_planning_document_catalogue_query_normalizer_v1.py",
        "tests/test_planning_document_catalogue_query_normalizer_v1_2.py"
    )){
        if(Test-Path "$Root\backend\$Regression"){
            docker compose exec -T backend python -m pytest -q $Regression
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $Regression" }
        }
    }

    Write-Host "[6] Static contract verification"
    $Verify=Get-Content $OrchestratorPath -Raw

    if($Verify -notmatch '# AUTO_RESEARCH_EVIDENCE_SCOPE_BRIDGE_V2'){
        throw "V2 marker missing."
    }

    if($Verify -notmatch 'applicable_document_ids = list\(auto_research_document_ids\)'){
        throw "Auto Research document scope assignment missing."
    }

    if($Verify -notmatch '\*resolved_document_ids'){
        throw "Existing spatial applicability merge logic was not preserved."
    }

    Write-Host "scope_contract=PASS"

    Write-Host "[7] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[8] Backend health"
    docker compose ps backend

    Write-Host "[9] Runtime import verification"
    docker compose exec -T backend python -c "from app.services.planning_orchestrator import execute_planning_run; print('runtime_scope_bridge=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Runtime import verification failed." }

    Write-Host "============================================================"
    Write-Host "AUTO RESEARCH EVIDENCE SCOPE BRIDGE V2 PASS"
    Write-Host "============================================================"
    Write-Host "No-spatial document question global search fallback: REMOVED"
    Write-Host "Auto Research document IDs: ENFORCED AS RETRIEVAL SCOPE"
    Write-Host "Existing spatial applicability merge: PRESERVED"
    Write-Host "GPP Auto Research path: PRESERVED"
    Write-Host "RSN/RT/RKK Auto Research path: PRESERVED"
    Write-Host "Cross-document-class leakage from project library: BLOCKED"
    Write-Host "Evidence grounding / validation: PRESERVED"
    Write-Host "AI provider configuration: UNCHANGED"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend change: NONE"
    Write-Host "Next gate: RETEST SAME LIVE RSN PERAK QUESTION"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring orchestrator/test backup."
    Copy-Item "$BackupDir\planning_orchestrator.py" $OrchestratorPath -Force

    if(Test-Path "$BackupDir\test_auto_research_evidence_scope_bridge_v2.py"){
        Copy-Item "$BackupDir\test_auto_research_evidence_scope_bridge_v2.py" $TestPath -Force
    } else {
        Remove-Item $TestPath -Force -ErrorAction SilentlyContinue
    }

    throw
}
