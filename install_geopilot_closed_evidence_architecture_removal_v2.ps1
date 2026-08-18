$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Config     = "$Root\backend\app\core\config.py"
$TrackB     = "$Root\backend\app\services\track_b.py"
$Acceptance = "$Root\backend\app\services\track_b_acceptance.py"
$AI         = "$Root\backend\app\services\track_b_ai.py"
$Workflow   = "$Root\backend\app\services\track_b_workflow.py"
$Frontend   = "$Root\frontend\src\pages\TrackBWorkspacePage.tsx"
$TestFile   = "$Root\backend\tests\test_controlled_evidence_architecture_v2.py"

$Required = @($Config,$TrackB,$Acceptance,$AI,$Workflow,$Frontend)
foreach($P in $Required){
    if(!(Test-Path $P)){ throw "Missing required source file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Closed Evidence Architecture Removal V2"
Write-Host "Closed/organizer-only enforcement -> provenance-controlled evidence"
Write-Host "NO DB SCHEMA CHANGE / NO MIGRATION"
Write-Host "============================================================"

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = "$Root\artifacts\closed_evidence_architecture_removal_v2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null

Copy-Item $Config     "$Backup\config.py"
Copy-Item $TrackB     "$Backup\track_b.py"
Copy-Item $Acceptance "$Backup\track_b_acceptance.py"
Copy-Item $AI         "$Backup\track_b_ai.py"
Copy-Item $Workflow   "$Backup\track_b_workflow.py"
Copy-Item $Frontend   "$Backup\TrackBWorkspacePage.tsx"
if(Test-Path $TestFile){ Copy-Item $TestFile "$Backup\test_controlled_evidence_architecture_v2.py" }
if(Test-Path "$Root\.env"){ Copy-Item "$Root\.env" "$Backup\.env" }
if(Test-Path "$Root\.env.example"){ Copy-Item "$Root\.env.example" "$Backup\.env.example" }

Write-Host "BACKUP: $Backup"

try {
    # ------------------------------------------------------------------
    # 0. Preflight: confirm audited architecture is still present.
    # ------------------------------------------------------------------
    Write-Host "[0] Preflight architecture gate"
    $configText = Get-Content $Config -Raw
    $trackText  = Get-Content $TrackB -Raw
    $aiText     = Get-Content $AI -Raw
    $frontText  = Get-Content $Frontend -Raw

    if($configText -notmatch 'track_b_competition_mode'){
        throw "Expected TRACK_B_COMPETITION_MODE setting is already absent. Stop to avoid patching an unknown state."
    }
    if($trackText -notmatch 'organizer-supplied uploads only; external acquisition is disabled'){
        throw "Expected organizer-only acquisition gate not found. Stop to avoid patching an unknown state."
    }
    if($aiText -notmatch 'closed Track B evidence boundary'){
        throw "Expected closed-evidence AI gate not found. Stop to avoid patching an unknown state."
    }
    if($frontText -notmatch 'CLOSED EVIDENCE MODE'){
        throw "Expected Closed Evidence Mode frontend marker not found. Stop to avoid patching an unknown state."
    }
    Write-Host "preflight_state=AUDIT_MATCH"

    # ------------------------------------------------------------------
    # 1. Config and ENV: remove competition-mode switch entirely.
    # ------------------------------------------------------------------
    Write-Host "[1] Remove competition-mode configuration"
    $t = Get-Content $Config -Raw
    $t = [regex]::Replace(
        $t,
        '(?m)^\s*track_b_competition_mode:\s*bool\s*=\s*Field\([^\r\n]*alias="TRACK_B_COMPETITION_MODE"[^\r\n]*\)\s*\r?\n',
        ''
    )
    Set-Content -Path $Config -Value $t -Encoding UTF8

    foreach($EnvPath in @("$Root\.env","$Root\.env.example")){
        if(Test-Path $EnvPath){
            $e = Get-Content $EnvPath -Raw
            $e = [regex]::Replace(
                $e,
                '(?m)^\s*TRACK_B_COMPETITION_MODE\s*=.*(?:\r?\n|$)',
                ''
            )
            Set-Content -Path $EnvPath -Value $e -Encoding UTF8
            Write-Host "cleaned: $EnvPath"
        }
    }

    # ------------------------------------------------------------------
    # 2. Track B core: remove admission and pair enforcement.
    #    Existing organizer provenance stays valid historical provenance.
    # ------------------------------------------------------------------
    Write-Host "[2] Remove organizer-only Track B enforcement"
    $t = Get-Content $TrackB -Raw

    $oldGuard = @'
def _assert_competition_upload(source_kind: str = "upload") -> None:
    settings = get_settings()
    if settings.track_b_competition_mode and source_kind != "upload":
        raise TrackBError("Track B competition mode accepts organizer-supplied uploads only; external acquisition is disabled.")
'@
    $newGuard = @'
def _assert_competition_upload(source_kind: str = "upload") -> None:
    """Compatibility hook retained for callers; evidence source is validated by provenance, not competition mode."""
    return None
'@
    if($t.Contains($oldGuard)){
        $t = $t.Replace($oldGuard,$newGuard)
    } else {
        $pattern = '(?ms)^def _assert_competition_upload\(source_kind: str = "upload"\) -> None:\r?\n.*?(?=^def )'
        if(-not [regex]::IsMatch($t,$pattern)){
            throw "Unable to locate competition upload guard safely."
        }
        $t = [regex]::Replace($t,$pattern,($newGuard + "`r`n`r`n"),1)
    }

    # Remove second temporal-pair competition gate.
    $pairGate = '(?ms)\s*if get_settings\(\)\.track_b_competition_mode and \(ds\.source_kind != "upload" or \(ds\.provenance or \{\}\)\.get\("evidence_scope"\) != "organizer_supplied_only"\):\s*raise TrackBError\("Competition mode rejected a raster that is not organizer-supplied evidence\."\)'
    $t = [regex]::Replace($t,$pairGate,'')

    # Generalize wording without weakening data-stage equivalence.
    $t = $t.Replace(
        'Temporal comparison must pair equivalent raw/raw or processed/processed organizer datasets.',
        'Temporal comparison must pair equivalent raw/raw or processed/processed datasets.'
    )
    $t = $t.Replace(
        'Organizer raster does not cover the selected Site geometry.',
        'Selected raster does not cover the selected Site geometry.'
    )
    $t = $t.Replace(
        'Cloud/shadow masking uses Sentinel SCL when supplied; otherwise it is limited to organizer-provided raster validity/nodata information.',
        'Cloud/shadow masking uses Sentinel SCL when supplied; otherwise it is limited to available raster validity/nodata information.'
    )

    # New uploads are user-supplied project evidence, not organizer-only evidence.
    $t = $t.Replace('provider="organizer"', 'provider="user_upload"')
    $t = $t.Replace('"evidence_scope": "organizer_supplied_only"', '"evidence_scope": "project_controlled"')

    # Analysis manifest evidence scope should follow the dataset provenance.
    $t = $t.Replace(
        '{"kind": "raster_dataset", "id": str(before.id), "checksum_sha256": before.checksum_sha256, "role": "before", "scope": "organizer_supplied_only"}',
        '{"kind": "raster_dataset", "id": str(before.id), "checksum_sha256": before.checksum_sha256, "role": "before", "scope": (before.provenance or {}).get("evidence_scope") or "project_controlled"}'
    )
    $t = $t.Replace(
        '{"kind": "raster_dataset", "id": str(after.id), "checksum_sha256": after.checksum_sha256, "role": "after", "scope": "organizer_supplied_only"}',
        '{"kind": "raster_dataset", "id": str(after.id), "checksum_sha256": after.checksum_sha256, "role": "after", "scope": (after.provenance or {}).get("evidence_scope") or "project_controlled"}'
    )

    # Report wording.
    $t = $t.Replace('Closed-evidence declaration','Evidence provenance declaration')
    $t = $t.Replace(
        'This analysis is configured for PLAN-Ai Hackathon 2026 Track B closed-evidence operation. Spatial measurements are derived from organizer-supplied raster evidence. GeoPilot is decision support and does not issue statutory approval or certification.',
        'This analysis uses evidence with recorded provenance and deterministic processing lineage. GeoPilot may combine project evidence, server-derived measurements, and approved official acquired sources. GeoPilot is decision support and does not issue statutory approval or certification.'
    )

    Set-Content -Path $TrackB -Value $t -Encoding UTF8

    # ------------------------------------------------------------------
    # 3. Acceptance/readiness: evidence quality replaces competition mode.
    # ------------------------------------------------------------------
    Write-Host "[3] Replace competition readiness with provenance readiness"
    $t = Get-Content $Acceptance -Raw

    # Generalize dataset selection.
    $organizerBlock = '(?ms)\s*organizer = \[\s*d for d in datasets\s*if .*?\]\s*'
    if([regex]::IsMatch($t,$organizerBlock)){
        $replacement = @'
    eligible = [
        d for d in datasets
        if not getattr(d, "is_archived", False)
        and bool(d.site_id)
        and bool(d.checksum_sha256)
        and bool(d.source_uri)
    ]

'@
        $t = [regex]::Replace($t,$organizerBlock,"`r`n" + $replacement,1)
    } else {
        throw "Readiness organizer dataset-selection block not found safely."
    }

    # Remove competition mode check.
    $competitionBlock = '(?ms)\s*checks\.append\(\{\s*"key": "competition_mode".*?\}\)\s*if not settings\.track_b_competition_mode:\s*blockers\.append\("Enable TRACK_B_COMPETITION_MODE before competition use\."\)\s*'
    $t = [regex]::Replace($t,$competitionBlock,"`r`n",1)

    $t = $t.Replace('_pair_payload(organizer, "urban")','_pair_payload(eligible, "urban")')
    $t = $t.Replace('_pair_payload(organizer, "rural")','_pair_payload(eligible, "rural")')
    $t = $t.Replace('Organizer-only before/after pair is locally available, lineage-verified, and analysis-compatible.','Before/after pair is locally available, lineage-verified, and analysis-compatible.')
    $t = $t.Replace('T1/T2 organizer pair','T1/T2 evidence pair')
    $t = $t.Replace('verify AI outputs against the organizer evidence','verify AI outputs against their cited evidence')
    $t = $t.Replace('"competition_mode": settings.track_b_competition_mode,','"evidence_architecture": "provenance_controlled",')
    $t = $t.Replace('"evidence_policy": "organizer_supplied_only",','"evidence_policy": "provenance_controlled",')
    $t = $t.Replace('"organizer_dataset_count": len(organizer),','"eligible_dataset_count": len(eligible),')

    Set-Content -Path $Acceptance -Value $t -Encoding UTF8

    # ------------------------------------------------------------------
    # 4. AI: remove source-scope rejection but preserve grounding.
    # ------------------------------------------------------------------
    Write-Host "[4] Convert Track B AI to provenance-controlled grounding"
    $t = Get-Content $AI -Raw

    # Three scope guards: interpretation, comparison, planner decision.
    $scopeGuard = '(?ms)\s*if not evidence or any\(e\.get\("scope"\) not in \{"organizer_supplied_only", "server_owned"\} for e in evidence\):\s*raise TrackBAIError\("[^"]*closed Track B evidence boundary\."\)'
    $count = ([regex]::Matches($t,$scopeGuard)).Count
    if($count -lt 3){
        throw "Expected at least three closed-evidence AI scope guards; found $count."
    }
    $t = [regex]::Replace(
        $t,
        $scopeGuard,
        "`r`n        if not evidence:`r`n            raise TrackBAIError(`"AI operation requires an evidence payload with provenance.`")"
    )

    $t = $t.Replace('CLOSED-EVIDENCE TRACK B FACTS:','GROUNDED TRACK B FACTS:')
    $t = $t.Replace('CLOSED-EVIDENCE URBAN/RURAL FACTS:','GROUNDED URBAN/RURAL FACTS:')
    $t = $t.Replace('CLOSED-EVIDENCE TRACK B DECISION FACTS:','GROUNDED TRACK B DECISION FACTS:')
    $t = $t.Replace('closed-evidence planning decision packet','provenance-controlled planning decision packet')
    $t = $t.Replace('Compare ONLY the supplied organizer-derived urban and rural temporal evidence.','Compare only the supplied grounded urban and rural temporal evidence.')
    $t = $t.Replace('Convert ONLY the supplied organizer-derived deterministic evidence into an auditable planner decision brief.','Convert only the supplied grounded evidence into an auditable planner decision brief.')

    # Keep deterministic evidence refs contract, but policy is no longer organizer-only.
    $t = $t.Replace('"evidence_policy": "organizer_supplied_only"','"evidence_policy": "provenance_controlled"')

    Set-Content -Path $AI -Value $t -Encoding UTF8

    # ------------------------------------------------------------------
    # 5. Workflow: select all provenance-valid project datasets.
    # ------------------------------------------------------------------
    Write-Host "[5] Generalize Track B workflow pair selection"
    $t = Get-Content $Workflow -Raw

    $oldSelect = '(?ms)\s*eligible = \[\s*d for d in datasets\s*if \(d\.provenance or \{\}\)\.get\("evidence_scope"\) == "organizer_supplied_only"\s*and \(d\.provenance or \{\}\)\.get\("competition_track"\) == "B"\s*.*?\]\s*'
    if([regex]::IsMatch($t,$oldSelect)){
        $newSelect = @'
    eligible = [
        d for d in datasets
        if not getattr(d, "is_archived", False)
        and bool(d.site_id)
        and bool(d.checksum_sha256)
        and bool(d.source_uri)
    ]

'@
        $t = [regex]::Replace($t,$oldSelect,"`r`n" + $newSelect,1)
    } else {
        # Audited source uses a short list-comprehension around lines 32-36.
        $t = [regex]::Replace(
            $t,
            '(?ms)\s*eligible = \[\s*d for d in datasets\s*if \(d\.provenance or \{\}\)\.get\("evidence_scope"\) == "organizer_supplied_only"\s*and \(d\.provenance or \{\}\)\.get\("competition_track"\) == "B"\s*\]',
            "`r`n    eligible = [d for d in datasets if not getattr(d, `"is_archived`", False) and bool(d.site_id) and bool(d.checksum_sha256) and bool(d.source_uri)]",
            1
        )
    }

    $t = $t.Replace('Hackathon simulation requires an organizer-supplied ','Workflow requires an eligible ')
    $t = $t.Replace('Grounded AI output generated inside the organizer-only evidence boundary.','Grounded AI output generated from provenance-controlled evidence.')
    $t = $t.Replace('"evidence_policy":"organizer_supplied_only"','"evidence_policy":"provenance_controlled"')

    Set-Content -Path $Workflow -Value $t -Encoding UTF8

    # ------------------------------------------------------------------
    # 6. Frontend: remove mode and organizer-only filtering/wording.
    # ------------------------------------------------------------------
    Write-Host "[6] Remove Closed Evidence Mode from frontend architecture"
    $t = Get-Content $Frontend -Raw

    $t = $t.Replace('// temporal question -> Track B closed-evidence decision flow','// temporal question -> Track B grounded decision flow')

    # Remove badge, not rename it.
    $t = [regex]::Replace(
        $t,
        '<div className="evidence-lock"><span className="pulse-dot"\s*/>\s*CLOSED EVIDENCE MODE<br\s*/><small>Organizer data only · external acquisition disabled</small></div>',
        '',
        1
    )

    # Generalize mission readiness filtering.
    $oldFrontendFilter = 'const organizer = datasets.filter((d) => d.provenance.evidence_scope === "organizer_supplied_only" && d.provenance.competition_track === "B" && Boolean(d.site_id));'
    $newFrontendFilter = 'const eligibleEvidence = datasets.filter((d) => Boolean(d.site_id) && Boolean(d.checksum_sha256) && Boolean(d.source_uri));'
    if(-not $t.Contains($oldFrontendFilter)){
        throw "Expected frontend organizer-only dataset filter not found."
    }
    $t = $t.Replace($oldFrontendFilter,$newFrontendFilter)
    $t = $t.Replace('const scoped = organizer.filter((d) => d.provenance.location_type === location);','const scoped = eligibleEvidence.filter((d) => d.provenance.location_type === location);')
    $t = $t.Replace('return { urban, rural, organizerCount: organizer.length, ready: urban && rural };','return { urban, rural, organizerCount: eligibleEvidence.length, ready: urban && rural };')

    $t = $t.Replace('Geospatial & Satellite AI workflow for organizer-supplied urban and rural temporal evidence.','Geospatial & Satellite AI workflow for provenance-controlled urban and rural temporal evidence.')
    $t = $t.Replace('<code>ORGANIZER_ONLY</code>','<code>PROVENANCE_CONTROLLED</code>')
    $t = $t.Replace('Register matching organizer-only Urban and Rural T1/T2 pairs with the same Site and data stage.','Register matching Urban and Rural T1/T2 evidence pairs with the same Site and data stage.')
    $t = $t.Replace('GeoPilot automatically selects organizer-only before/after pairs for both challenge contexts, runs deterministic temporal analysis, grounded AI interpretation, planner decision briefs, and strategic comparison.','GeoPilot automatically selects eligible before/after evidence pairs for both contexts, runs deterministic temporal analysis, grounded AI interpretation, planner decision briefs, and strategic comparison.')

    Set-Content -Path $Frontend -Value $t -Encoding UTF8

    # ------------------------------------------------------------------
    # 7. New architecture test.
    # ------------------------------------------------------------------
    Write-Host "[7] Install architecture regression test"
    $test = @'
from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def test_closed_evidence_architecture_removed():
    config = _read("app/core/config.py")
    track = _read("app/services/track_b.py")
    acceptance = _read("app/services/track_b_acceptance.py")
    ai = _read("app/services/track_b_ai.py")
    workflow = _read("app/services/track_b_workflow.py")

    joined = "\n".join([config, track, acceptance, ai, workflow]).casefold()
    assert "track_b_competition_mode" not in joined
    assert "closed-evidence" not in joined
    assert "closed evidence mode" not in joined
    assert "external acquisition is disabled" not in joined
    assert "closed track b evidence boundary" not in joined


def test_provenance_controlled_policy_present():
    acceptance = _read("app/services/track_b_acceptance.py")
    ai = _read("app/services/track_b_ai.py")
    workflow = _read("app/services/track_b_workflow.py")
    assert "provenance_controlled" in acceptance
    assert "provenance_controlled" in ai
    assert "provenance_controlled" in workflow


def test_grounding_safeguards_preserved():
    ai = _read("app/services/track_b_ai.py")
    assert "Never invent" in ai
    assert "NUMERIC GROUNDING RULE" in ai
    assert "_validate_no_invented_numbers" in ai
    assert "_validate_decision_numbers" in ai


def test_terrain_router_preserved():
    ai = _read("app/services/track_b_ai.py")
    assert "TRACKB_TERRAIN_DECISION_ROUTER_V2" in ai
    assert "terrain.site_summary" in ai


def test_auto_research_markers_preserved():
    orchestrator = _read("app/services/planning_orchestrator.py")
    assert "AUTO_RESEARCH_QUESTION_ROUTER_V1" in orchestrator
    assert "AUTO_RESEARCH_EVIDENCE_BRIDGE_V1" in orchestrator
'@
    Set-Content -Path $TestFile -Value $test -Encoding UTF8

    # ------------------------------------------------------------------
    # 8. Source audit.
    # ------------------------------------------------------------------
    Write-Host "[8] Architectural residual audit"
    $allSource = @($Config,$TrackB,$Acceptance,$AI,$Workflow,$Frontend)
    $forbidden = @(
        'TRACK_B_COMPETITION_MODE',
        'track_b_competition_mode',
        'CLOSED EVIDENCE MODE',
        'CLOSED-EVIDENCE',
        'closed-evidence',
        'closed Track B evidence boundary',
        'external acquisition is disabled',
        'Organizer-only evidence enforcement'
    )

    $residual = @()
    foreach($P in $allSource){
        $body = Get-Content $P -Raw
        foreach($needle in $forbidden){
            if($body -match [regex]::Escape($needle)){
                $residual += "$P :: $needle"
            }
        }
    }
    if($residual.Count){
        $residual | ForEach-Object { Write-Host "RESIDUAL: $_" }
        throw "Closed Evidence architecture residuals remain."
    }
    Write-Host "closed_evidence_architecture_residuals=NONE"

    # ------------------------------------------------------------------
    # 9. Syntax / frontend build.
    # ------------------------------------------------------------------
    Write-Host "[9] Backend syntax checks"
    docker compose exec -T backend python -m py_compile `
        app/core/config.py `
        app/services/track_b.py `
        app/services/track_b_acceptance.py `
        app/services/track_b_ai.py `
        app/services/track_b_workflow.py `
        tests/test_controlled_evidence_architecture_v2.py
    if($LASTEXITCODE-ne 0){ throw "Backend syntax check failed." }

    Write-Host "[10] New architecture tests"
    docker compose exec -T backend python -m pytest -q tests/test_controlled_evidence_architecture_v2.py
    if($LASTEXITCODE-ne 0){ throw "Architecture regression tests failed." }

    Write-Host "[11] Preserve Auto Research / retrieval / terrain tests"
    foreach($T in @(
        "tests/test_planning_document_auto_research.py",
        "tests/test_planning_document_acquisition.py",
        "tests/test_document_retrieval.py",
        "tests/test_terrain_analysis.py",
        "tests/test_terrain_acquisition.py"
    )){
        if(Test-Path "$Root\backend\$T"){
            docker compose exec -T backend python -m pytest -q $T
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $T" }
        }
    }

    Write-Host "[12] Track B safety regression subset"
    if(Test-Path "$Root\backend\tests\test_track_b_hackathon.py"){
        docker compose exec -T backend python -m pytest -q tests/test_track_b_hackathon.py -k "numeric or terrain or planner_decision or recommended_mode"
        if($LASTEXITCODE-ne 0){ throw "Track B safety regression subset failed." }
    }

    Write-Host "[13] Frontend production build"
    docker compose exec -T frontend npm run build
    if($LASTEXITCODE-ne 0){ throw "Frontend build failed." }

    # ------------------------------------------------------------------
    # 14. Runtime reload.
    # ------------------------------------------------------------------
    Write-Host "[14] Recreate backend only to reload ENV/config; restart frontend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }
    docker compose restart frontend
    if($LASTEXITCODE-ne 0){ throw "Frontend restart failed." }

    Start-Sleep -Seconds 5

    Write-Host "[15] Runtime verification"
    docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); assert not hasattr(s,'track_b_competition_mode'); print('competition_mode_attribute=REMOVED'); print('ai_provider=',s.ai_provider); print('ai_fallback_provider=',s.ai_fallback_provider)"
    if($LASTEXITCODE-ne 0){ throw "Runtime config verification failed." }

    Write-Host "[16] Service health"
    docker compose ps

    Write-Host "============================================================"
    Write-Host "CLOSED EVIDENCE ARCHITECTURE REMOVAL V2 PASS"
    Write-Host "============================================================"
    Write-Host "Closed Evidence Mode: REMOVED"
    Write-Host "TRACK_B_COMPETITION_MODE: REMOVED"
    Write-Host "Organizer-only acquisition block: REMOVED"
    Write-Host "Organizer-only temporal-pair block: REMOVED"
    Write-Host "Organizer-only readiness filter: REMOVED"
    Write-Host "Organizer-only workflow pair selector: REMOVED"
    Write-Host "Closed-evidence AI scope rejection: REMOVED"
    Write-Host "Frontend Closed Evidence badge: REMOVED"
    Write-Host "Frontend organizer-only dataset filter: REMOVED"
    Write-Host "Evidence architecture: PROVENANCE CONTROLLED"
    Write-Host "User/project evidence: ALLOWED"
    Write-Host "Official acquired evidence: ALLOWED BY ARCHITECTURE"
    Write-Host "Server-derived deterministic evidence: ALLOWED"
    Write-Host "Existing organizer evidence: PRESERVED AS HISTORICAL PROVENANCE"
    Write-Host "Auto Research RT/RSN/RKK/GPP: PRESERVED"
    Write-Host "Terrain auto acquisition + terrain.site_summary: PRESERVED"
    Write-Host "OpenAI/Ollama provider order: UNCHANGED"
    Write-Host "Anti-hallucination: PRESERVED"
    Write-Host "Numeric grounding: PRESERVED"
    Write-Host "Professional review boundary: PRESERVED"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Next gate: LIVE UI + document-evidence E2E"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring full backup."
    Copy-Item "$Backup\config.py" $Config -Force
    Copy-Item "$Backup\track_b.py" $TrackB -Force
    Copy-Item "$Backup\track_b_acceptance.py" $Acceptance -Force
    Copy-Item "$Backup\track_b_ai.py" $AI -Force
    Copy-Item "$Backup\track_b_workflow.py" $Workflow -Force
    Copy-Item "$Backup\TrackBWorkspacePage.tsx" $Frontend -Force

    if(Test-Path "$Backup\test_controlled_evidence_architecture_v2.py"){
        Copy-Item "$Backup\test_controlled_evidence_architecture_v2.py" $TestFile -Force
    } else {
        Remove-Item $TestFile -Force -ErrorAction SilentlyContinue
    }

    if(Test-Path "$Backup\.env"){ Copy-Item "$Backup\.env" "$Root\.env" -Force }
    if(Test-Path "$Backup\.env.example"){ Copy-Item "$Backup\.env.example" "$Root\.env.example" -Force }

    throw
}
