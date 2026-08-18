$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$ApiPath="$Root\backend\app\api\v1\track_b.py"
$TestPath="$Root\backend\tests\test_track_b_decision_workspace_response_presentation_v2.py"

if(!(Test-Path $ApiPath)){ throw "Missing required file: $ApiPath" }

Write-Host "============================================================"
Write-Host "GeoPilot Decision Workspace Response Presentation V2"
Write-Host "Planning implication = grounded synthesis"
Write-Host "Evidence summary = deterministic evidence/source summary"
Write-Host "NO DB SCHEMA CHANGE / NO MIGRATION / NO FRONTEND SOURCE CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\decision_workspace_response_presentation_v2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $ApiPath "$Backup\track_b.py"
if(Test-Path $TestPath){ Copy-Item $TestPath "$Backup\test_track_b_decision_workspace_response_presentation_v2.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Preflight duplication gate"
    $Text=Get-Content $ApiPath -Raw
    if($Text -notmatch '"planning_implication": synthesis'){ throw "planning_implication=synthesis not found." }
    if($Text -notmatch '"evidence_summary": synthesis'){ throw "evidence_summary=synthesis duplication not found." }
    Write-Host "duplication_state=CONFIRMED"

    Write-Host "[1] Patch adapter host-side"

    $Old = @'
    completed = run.status == "completed" and bool(run.synthesis)
    synthesis = (run.synthesis or "").strip()
    if not synthesis:
        synthesis = "GeoPilot could not produce a grounded planning answer from the currently available validated evidence."
    return {
'@

    $New = @'
    completed = run.status == "completed" and bool(run.synthesis)
    synthesis = (run.synthesis or "").strip()
    if not synthesis:
        synthesis = "GeoPilot could not produce a grounded planning answer from the currently available validated evidence."

    evidence_summary_lines = []
    seen_summary_lines = set()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") or {}
        tool_name = str(item.get("tool_name") or "validated_evidence")

        if tool_name == "documents.search":
            title = str(payload.get("document_title") or "").strip()
            citation = str(payload.get("citation_label") or "").strip()
            authority = str(payload.get("authority") or "").strip()
            page_number = payload.get("page_number")

            label = title or citation or "Planning document evidence"
            details = []
            if authority and authority.casefold() not in label.casefold():
                details.append(authority)
            if citation and citation != label:
                details.append(citation)
            elif page_number is not None and f"p. {page_number}" not in label:
                details.append(f"p. {page_number}")

            line = f"- **{label}**"
            if details:
                line += " — " + " · ".join(details)
        else:
            line = f"- **{tool_name}** — validated project evidence"

        if line not in seen_summary_lines:
            seen_summary_lines.add(line)
            evidence_summary_lines.append(line)

    if evidence_summary_lines:
        evidence_summary = "### Validated evidence used\n" + "\n".join(evidence_summary_lines)
    elif refs:
        evidence_summary = "### Validated evidence references\n" + "\n".join(f"- {ref}" for ref in refs)
    else:
        evidence_summary = "No validated evidence reference was available for this response."

    return {
'@

    if(-not $Text.Contains($Old.TrimStart("`r","`n"))){
        throw "Expected adapter block not found."
    }

    $Text=$Text.Replace($Old.TrimStart("`r","`n"),$New.TrimStart("`r","`n"))
    $Text=$Text.Replace('        "evidence_summary": synthesis,','        "evidence_summary": evidence_summary,')

    [System.IO.File]::WriteAllText($ApiPath,$Text,[System.Text.UTF8Encoding]::new($false))
    Write-Host "PATCHED: $ApiPath"

    Write-Host "[2] Install focused regression tests"
    $TestText = @'
from types import SimpleNamespace
import uuid

from app.api.v1.track_b import _planning_run_to_track_b_decision


def test_separates_synthesis_and_evidence_summary():
    run = SimpleNamespace(
        status="completed",
        synthesis="## Grounded answer\nUse this as the planning answer.",
        provider_metadata={"provider": "openai", "model": "test"},
        evidence=[
            {
                "tool_name": "documents.search",
                "payload": {
                    "document_title": "GPP Pembangunan Di Kawasan Bukit dan Tanah Tinggi",
                    "citation_label": "GPP Bukit dan Tanah Tinggi, p. 19",
                    "authority": "PLANMalaysia",
                    "page_number": 19,
                },
            }
        ],
        limitations=[],
    )
    result = _planning_run_to_track_b_decision(
        analysis_id=uuid.uuid4(),
        question="Apakah kategori ketinggian?",
        run=run,
    )
    assert result["planning_implication"] == run.synthesis
    assert result["evidence_summary"] != run.synthesis
    assert "Validated evidence used" in result["evidence_summary"]
    assert "GPP Pembangunan Di Kawasan Bukit dan Tanah Tinggi" in result["evidence_summary"]
    assert "p. 19" in result["evidence_summary"]


def test_deduplicates_same_evidence_line():
    item = {
        "tool_name": "documents.search",
        "payload": {
            "document_title": "Official RT",
            "citation_label": "Official RT, p. 12",
            "authority": "PLANMalaysia",
            "page_number": 12,
        },
    }
    run = SimpleNamespace(
        status="completed",
        synthesis="Answer",
        provider_metadata={},
        evidence=[item, item],
        limitations=[],
    )
    result = _planning_run_to_track_b_decision(
        analysis_id=uuid.uuid4(),
        question="Q",
        run=run,
    )
    assert result["evidence_summary"].count("**Official RT**") == 1


def test_no_evidence_does_not_duplicate_answer():
    run = SimpleNamespace(
        status="completed",
        synthesis="Unique answer",
        provider_metadata={},
        evidence=[],
        limitations=[],
    )
    result = _planning_run_to_track_b_decision(
        analysis_id=uuid.uuid4(),
        question="Q",
        run=run,
    )
    assert result["evidence_summary"] != result["planning_implication"]
'@
    [System.IO.File]::WriteAllText($TestPath,$TestText,[System.Text.UTF8Encoding]::new($false))

    Write-Host "[3] Syntax check"
    docker compose exec -T backend python -m py_compile app/api/v1/track_b.py tests/test_track_b_decision_workspace_response_presentation_v2.py
    if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

    Write-Host "[4] Focused adapter tests"
    docker compose exec -T backend python -m pytest -q tests/test_track_b_decision_workspace_response_presentation_v2.py
    if($LASTEXITCODE-ne 0){ throw "Focused adapter tests failed." }

    Write-Host "[5] Preserve key dispatcher regressions"
    foreach($T in @(
        "tests/test_track_b_planning_question_dispatcher_v1.py",
        "tests/test_track_b_planning_question_dispatcher_manifest_v1_2.py"
    )){
        if(Test-Path "$Root\backend\$T"){
            docker compose exec -T backend python -m pytest -q $T
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $T" }
        }
    }

    Write-Host "[6] Static contract verification"
    $Verify=Get-Content $ApiPath -Raw
    if($Verify -match '"evidence_summary": synthesis'){ throw "Duplication remains." }
    if($Verify -notmatch '"evidence_summary": evidence_summary'){ throw "Deterministic evidence summary missing." }
    if($Verify -notmatch '"planning_implication": synthesis'){ throw "Planning synthesis was not preserved." }
    Write-Host "adapter_contract=PASS"

    Write-Host "[7] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[8] Backend health"
    docker compose ps backend

    Write-Host "============================================================"
    Write-Host "DECISION WORKSPACE RESPONSE PRESENTATION V2 PASS"
    Write-Host "============================================================"
    Write-Host "Planning implication: GROUNDED SYNTHESIS PRESERVED"
    Write-Host "Evidence summary: DETERMINISTIC SOURCE SUMMARY"
    Write-Host "Planning/evidence duplication: REMOVED"
    Write-Host "Document title/citation/page identity: PRESERVED"
    Write-Host "Auto Research: UNCHANGED"
    Write-Host "AI provider configuration: UNCHANGED"
    Write-Host "Frontend markdown renderer: UNCHANGED"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Next gate: RETEST SAME LIVE GPP QUESTION"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring backend/test backup."
    Copy-Item "$Backup\track_b.py" $ApiPath -Force
    if(Test-Path "$Backup\test_track_b_decision_workspace_response_presentation_v2.py"){
        Copy-Item "$Backup\test_track_b_decision_workspace_response_presentation_v2.py" $TestPath -Force
    } else {
        Remove-Item $TestPath -Force -ErrorAction SilentlyContinue
    }
    throw
}
