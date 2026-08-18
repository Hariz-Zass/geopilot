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
$TestFile   = "$Root\backend\tests\test_controlled_evidence_architecture_v2_1.py"

$Required = @($Config,$TrackB,$Acceptance,$AI,$Workflow,$Frontend)
foreach($P in $Required){
    if(!(Test-Path $P)){ throw "Missing required source file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Closed Evidence Architecture Removal V2.1"
Write-Host "Recovery for V2 acceptance indentation failure"
Write-Host "NO DB SCHEMA CHANGE / NO MIGRATION"
Write-Host "============================================================"

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = "$Root\artifacts\closed_evidence_architecture_removal_v2_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null

Copy-Item $Config     "$Backup\config.py"
Copy-Item $TrackB     "$Backup\track_b.py"
Copy-Item $Acceptance "$Backup\track_b_acceptance.py"
Copy-Item $AI         "$Backup\track_b_ai.py"
Copy-Item $Workflow   "$Backup\track_b_workflow.py"
Copy-Item $Frontend   "$Backup\TrackBWorkspacePage.tsx"
if(Test-Path $TestFile){ Copy-Item $TestFile "$Backup\test_controlled_evidence_architecture_v2_1.py" }
if(Test-Path "$Root\.env"){ Copy-Item "$Root\.env" "$Backup\.env" }
if(Test-Path "$Root\.env.example"){ Copy-Item "$Root\.env.example" "$Backup\.env.example" }

Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Confirm V2 rollback restored audited source"
    $configText = Get-Content $Config -Raw
    $trackText = Get-Content $TrackB -Raw
    $acceptText = Get-Content $Acceptance -Raw
    $aiText = Get-Content $AI -Raw
    $frontText = Get-Content $Frontend -Raw

    if($configText -notmatch 'track_b_competition_mode'){ throw "Rollback gate failed: competition setting absent." }
    if($trackText -notmatch 'external acquisition is disabled'){ throw "Rollback gate failed: Track B acquisition gate absent." }
    if($acceptText -notmatch '"key": "competition_mode"'){ throw "Rollback gate failed: acceptance competition gate absent." }
    if($aiText -notmatch 'closed Track B evidence boundary'){ throw "Rollback gate failed: AI closed-evidence gate absent." }
    if($frontText -notmatch 'CLOSED EVIDENCE MODE'){ throw "Rollback gate failed: frontend marker absent." }
    Write-Host "rollback_state=CONFIRMED"

    Write-Host "[1] Remove competition-mode config + ENV"
    $t = Get-Content $Config -Raw
    $t = [regex]::Replace(
        $t,
        '(?m)^\s*track_b_competition_mode:\s*bool\s*=\s*Field\([^\r\n]*alias="TRACK_B_COMPETITION_MODE"[^\r\n]*\)\s*\r?\n',
        ''
    )
    Set-Content $Config $t -Encoding UTF8

    foreach($EnvPath in @("$Root\.env","$Root\.env.example")){
        if(Test-Path $EnvPath){
            $e = Get-Content $EnvPath -Raw
            $e = [regex]::Replace($e,'(?m)^\s*TRACK_B_COMPETITION_MODE\s*=.*(?:\r?\n|$)','')
            Set-Content $EnvPath $e -Encoding UTF8
            Write-Host "cleaned: $EnvPath"
        }
    }

    Write-Host "[2] Remove Track B organizer-only enforcement"
    $t = Get-Content $TrackB -Raw

    $guardPattern = '(?ms)^def _assert_competition_upload\(source_kind: str = "upload"\) -> None:\r?\n.*?(?=^def )'
    if(-not [regex]::IsMatch($t,$guardPattern)){ throw "Track B upload guard boundary not found." }
    $guardReplacement = @'
def _assert_competition_upload(source_kind: str = "upload") -> None:
    """Compatibility hook retained for callers; source eligibility is provenance-based."""
    return None


'@
    $t = [regex]::Replace($t,$guardPattern,$guardReplacement,1)

    $pairGate = '(?ms)\s*if get_settings\(\)\.track_b_competition_mode and \(ds\.source_kind != "upload" or \(ds\.provenance or \{\}\)\.get\("evidence_scope"\) != "organizer_supplied_only"\):\s*raise TrackBError\("Competition mode rejected a raster that is not organizer-supplied evidence\."\)'
    $t = [regex]::Replace($t,$pairGate,'')

    $t = $t.Replace(
        'Temporal comparison must pair equivalent raw/raw or processed/processed organizer datasets.',
        'Temporal comparison must pair equivalent raw/raw or processed/processed datasets.'
    )
    $t = $t.Replace('Organizer raster does not cover the selected Site geometry.','Selected raster does not cover the selected Site geometry.')
    $t = $t.Replace(
        'Cloud/shadow masking uses Sentinel SCL when supplied; otherwise it is limited to organizer-provided raster validity/nodata information.',
        'Cloud/shadow masking uses Sentinel SCL when supplied; otherwise it is limited to available raster validity/nodata information.'
    )
    $t = $t.Replace('provider="organizer"','provider="user_upload"')
    $t = $t.Replace('"evidence_scope": "organizer_supplied_only"','"evidence_scope": "project_controlled"')

    $t = $t.Replace(
        '{"kind": "raster_dataset", "id": str(before.id), "checksum_sha256": before.checksum_sha256, "role": "before", "scope": "organizer_supplied_only"}',
        '{"kind": "raster_dataset", "id": str(before.id), "checksum_sha256": before.checksum_sha256, "role": "before", "scope": (before.provenance or {}).get("evidence_scope") or "project_controlled"}'
    )
    $t = $t.Replace(
        '{"kind": "raster_dataset", "id": str(after.id), "checksum_sha256": after.checksum_sha256, "role": "after", "scope": "organizer_supplied_only"}',
        '{"kind": "raster_dataset", "id": str(after.id), "checksum_sha256": after.checksum_sha256, "role": "after", "scope": (after.provenance or {}).get("evidence_scope") or "project_controlled"}'
    )

    $t = $t.Replace('Closed-evidence declaration','Evidence provenance declaration')
    $t = $t.Replace(
        'This analysis is configured for PLAN-Ai Hackathon 2026 Track B closed-evidence operation. Spatial measurements are derived from organizer-supplied raster evidence. GeoPilot is decision support and does not issue statutory approval or certification.',
        'This analysis uses evidence with recorded provenance and deterministic processing lineage. GeoPilot may combine project evidence, server-derived measurements, and approved official acquired sources. GeoPilot is decision support and does not issue statutory approval or certification.'
    )
    Set-Content $TrackB $t -Encoding UTF8

    Write-Host "[3] Patch acceptance readiness without rewriting block indentation"
    $t = Get-Content $Acceptance -Raw

    # Keep the existing list-comprehension structure and variable name, but remove
    # the two organizer-only predicates. This avoids reconstructing indentation.
    $t = [regex]::Replace(
        $t,
        '(?m)^\s*and \(d\.provenance or \{\}\)\.get\("evidence_scope"\) == "organizer_supplied_only"\s*\r?\n',
        ''
    )
    $t = [regex]::Replace(
        $t,
        '(?m)^\s*and \(d\.provenance or \{\}\)\.get\("competition_track"\) == "B"\s*\r?\n',
        ''
    )

    # Remove the whole checks.append competition-mode block using line-based bounds.
    $lines = $t -split "`r?`n"
    $out = New-Object System.Collections.Generic.List[string]
    $skip = $false
    $depth = 0
    $removedCompetitionCheck = $false
    for($i=0; $i -lt $lines.Count; $i++){
        $line = $lines[$i]

        if(-not $skip -and $line -match '"key": "competition_mode"'){
            # Remove already-buffered opening lines for this checks.append block.
            while($out.Count -gt 0 -and $out[$out.Count-1] -notmatch 'checks\.append\(\{'){
                $out.RemoveAt($out.Count-1)
            }
            if($out.Count -gt 0 -and $out[$out.Count-1] -match 'checks\.append\(\{'){
                $out.RemoveAt($out.Count-1)
            }
            $skip = $true
            $removedCompetitionCheck = $true
            continue
        }

        if($skip){
            if($line -match '^\s*\}\)\s*$'){
                $skip = $false
            }
            continue
        }

        # Remove the following two-line blocker if present.
        if($line -match '^\s*if not settings\.track_b_competition_mode:\s*$'){
            if($i + 1 -lt $lines.Count -and $lines[$i+1] -match 'Enable TRACK_B_COMPETITION_MODE before competition use'){
                $i++
                continue
            }
        }

        $out.Add($line)
    }
    if(-not $removedCompetitionCheck){ throw "Acceptance competition check block not found." }
    $t = ($out -join "`r`n")

    $t = $t.Replace('Organizer-only before/after pair is locally available, lineage-verified, and analysis-compatible.','Before/after pair is locally available, lineage-verified, and analysis-compatible.')
    $t = $t.Replace('T1/T2 organizer pair','T1/T2 evidence pair')
    $t = $t.Replace('verify AI outputs against the organizer evidence','verify AI outputs against their cited evidence')
    $t = $t.Replace('"competition_mode": settings.track_b_competition_mode,','"evidence_architecture": "provenance_controlled",')
    $t = $t.Replace('"evidence_policy": "organizer_supplied_only",','"evidence_policy": "provenance_controlled",')
    $t = $t.Replace('"organizer_dataset_count": len(organizer),','"eligible_dataset_count": len(organizer),')

    Set-Content $Acceptance $t -Encoding UTF8

    Write-Host "[4] Convert Track B AI to provenance-controlled grounding"
    $t = Get-Content $AI -Raw

    $scopeGuard = '(?ms)\s*if not evidence or any\(e\.get\("scope"\) not in \{"organizer_supplied_only", "server_owned"\} for e in evidence\):\s*raise TrackBAIError\("[^"]*closed Track B evidence boundary\."\)'
    $guardCount = ([regex]::Matches($t,$scopeGuard)).Count
    if($guardCount -lt 3){ throw "Expected >=3 AI closed-evidence guards; found $guardCount." }

    $t = [regex]::Replace(
        $t,
        $scopeGuard,
        "`r`n    if not evidence:`r`n        raise TrackBAIError(`"AI operation requires an evidence payload with provenance.`")"
    )

    $t = $t.Replace('CLOSED-EVIDENCE TRACK B FACTS:','GROUNDED TRACK B FACTS:')
    $t = $t.Replace('CLOSED-EVIDENCE URBAN/RURAL FACTS:','GROUNDED URBAN/RURAL FACTS:')
    $t = $t.Replace('CLOSED-EVIDENCE TRACK B DECISION FACTS:','GROUNDED TRACK B DECISION FACTS:')
    $t = $t.Replace('closed-evidence planning decision packet','provenance-controlled planning decision packet')
    $t = $t.Replace('Compare ONLY the supplied organizer-derived urban and rural temporal evidence.','Compare only the supplied grounded urban and rural temporal evidence.')
    $t = $t.Replace('Convert ONLY the supplied organizer-derived deterministic evidence into an auditable planner decision brief.','Convert only the supplied grounded evidence into an auditable planner decision brief.')
    $t = $t.Replace('"evidence_policy": "organizer_supplied_only"','"evidence_policy": "provenance_controlled"')
    Set-Content $AI $t -Encoding UTF8

    Write-Host "[5] Generalize workflow pair selector without rebuilding indentation"
    $t = Get-Content $Workflow -Raw
    $t = [regex]::Replace(
        $t,
        '(?m)^\s*if \(d\.provenance or \{\}\)\.get\("evidence_scope"\) == "organizer_supplied_only"\s*\r?\n',
        '        if not getattr(d, "is_archived", False)' + "`r`n"
    )
    $t = [regex]::Replace(
        $t,
        '(?m)^\s*and \(d\.provenance or \{\}\)\.get\("competition_track"\) == "B"\s*\r?\n',
        '        and bool(d.site_id)' + "`r`n" +
        '        and bool(d.checksum_sha256)' + "`r`n" +
        '        and bool(d.source_uri)' + "`r`n"
    )
    $t = $t.Replace('Hackathon simulation requires an organizer-supplied ','Workflow requires an eligible ')
    $t = $t.Replace('Grounded AI output generated inside the organizer-only evidence boundary.','Grounded AI output generated from provenance-controlled evidence.')
    $t = $t.Replace('"evidence_policy":"organizer_supplied_only"','"evidence_policy":"provenance_controlled"')
    Set-Content $Workflow $t -Encoding UTF8

    Write-Host "[6] Remove frontend closed mode + organizer-only filter"
    $t = Get-Content $Frontend -Raw
    $t = $t.Replace('// temporal question -> Track B closed-evidence decision flow','// temporal question -> Track B grounded decision flow')
    $t = [regex]::Replace(
        $t,
        '<div className="evidence-lock"><span className="pulse-dot"\s*/>\s*CLOSED EVIDENCE MODE<br\s*/><small>Organizer data only · external acquisition disabled</small></div>',
        '',
        1
    )

    $oldFilter = 'const organizer = datasets.filter((d) => d.provenance.evidence_scope === "organizer_supplied_only" && d.provenance.competition_track === "B" && Boolean(d.site_id));'
    if(-not $t.Contains($oldFilter)){ throw "Frontend organizer-only filter not found." }
    $t = $t.Replace(
        $oldFilter,
        'const eligibleEvidence = datasets.filter((d) => Boolean(d.site_id) && Boolean(d.checksum_sha256) && Boolean(d.source_uri));'
    )
    $t = $t.Replace('const scoped = organizer.filter((d) => d.provenance.location_type === location);','const scoped = eligibleEvidence.filter((d) => d.provenance.location_type === location);')
    $t = $t.Replace('return { urban, rural, organizerCount: organizer.length, ready: urban && rural };','return { urban, rural, organizerCount: eligibleEvidence.length, ready: urban && rural };')
    $t = $t.Replace('Geospatial & Satellite AI workflow for organizer-supplied urban and rural temporal evidence.','Geospatial & Satellite AI workflow for provenance-controlled urban and rural temporal evidence.')
    $t = $t.Replace('<code>ORGANIZER_ONLY</code>','<code>PROVENANCE_CONTROLLED</code>')
    $t = $t.Replace('Register matching organizer-only Urban and Rural T1/T2 pairs with the same Site and data stage.','Register matching Urban and Rural T1/T2 evidence pairs with the same Site and data stage.')
    $t = $t.Replace('GeoPilot automatically selects organizer-only before/after pairs for both challenge contexts, runs deterministic temporal analysis, grounded AI interpretation, planner decision briefs, and strategic comparison.','GeoPilot automatically selects eligible before/after evidence pairs for both contexts, runs deterministic temporal analysis, grounded AI interpretation, planner decision briefs, and strategic comparison.')
    Set-Content $Frontend $t -Encoding UTF8

    Write-Host "[7] Install focused architecture regression tests"
    $test = @'
from pathlib import Path

def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig")

def test_closed_mode_removed_from_backend_architecture():
    paths = [
        "app/core/config.py",
        "app/services/track_b.py",
        "app/services/track_b_acceptance.py",
        "app/services/track_b_ai.py",
        "app/services/track_b_workflow.py",
    ]
    text = "\n".join(read(p) for p in paths).casefold()
    for forbidden in (
        "track_b_competition_mode",
        "closed-evidence",
        "closed track b evidence boundary",
        "external acquisition is disabled",
    ):
        assert forbidden not in text

def test_provenance_architecture_present():
    assert "provenance_controlled" in read("app/services/track_b_acceptance.py")
    assert "provenance_controlled" in read("app/services/track_b_ai.py")
    assert "provenance_controlled" in read("app/services/track_b_workflow.py")

def test_anti_hallucination_and_numeric_grounding_preserved():
    ai = read("app/services/track_b_ai.py")
    assert "Never invent" in ai
    assert "NUMERIC GROUNDING RULE" in ai
    assert "_validate_no_invented_numbers" in ai
    assert "_validate_decision_numbers" in ai

def test_terrain_and_auto_research_markers_preserved():
    ai = read("app/services/track_b_ai.py")
    orchestrator = read("app/services/planning_orchestrator.py")
    assert "TRACKB_TERRAIN_DECISION_ROUTER_V2" in ai
    assert "terrain.site_summary" in ai
    assert "AUTO_RESEARCH_QUESTION_ROUTER_V1" in orchestrator
    assert "AUTO_RESEARCH_EVIDENCE_BRIDGE_V1" in orchestrator
'@
    Set-Content $TestFile $test -Encoding UTF8

    Write-Host "[8] Syntax gate BEFORE any regression tests"
    docker compose exec -T backend python -m py_compile `
        app/core/config.py `
        app/services/track_b.py `
        app/services/track_b_acceptance.py `
        app/services/track_b_ai.py `
        app/services/track_b_workflow.py `
        tests/test_controlled_evidence_architecture_v2_1.py
    if($LASTEXITCODE-ne 0){ throw "Backend syntax gate failed." }

    Write-Host "[9] Residual architecture audit"
    $allSource = @($Config,$TrackB,$Acceptance,$AI,$Workflow,$Frontend)
    $forbidden = @(
        'TRACK_B_COMPETITION_MODE',
        'track_b_competition_mode',
        'CLOSED EVIDENCE MODE',
        'CLOSED-EVIDENCE',
        'closed-evidence',
        'closed Track B evidence boundary',
        'external acquisition is disabled'
    )
    $residual = @()
    foreach($P in $allSource){
        $body = Get-Content $P -Raw
        foreach($needle in $forbidden){
            if($body -match [regex]::Escape($needle)){ $residual += "$P :: $needle" }
        }
    }
    if($residual.Count){
        $residual | ForEach-Object { Write-Host "RESIDUAL: $_" }
        throw "Closed Evidence residuals remain."
    }
    Write-Host "closed_evidence_architecture_residuals=NONE"

    Write-Host "[10] Focused architecture tests"
    docker compose exec -T backend python -m pytest -q tests/test_controlled_evidence_architecture_v2_1.py
    if($LASTEXITCODE-ne 0){ throw "Architecture tests failed." }

    Write-Host "[11] Preserve planning document + terrain regressions"
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
        if($LASTEXITCODE-ne 0){ throw "Track B safety subset failed." }
    }

    Write-Host "[13] Frontend production build"
    docker compose exec -T frontend npm run build
    if($LASTEXITCODE-ne 0){ throw "Frontend build failed." }

    Write-Host "[14] Reload runtime"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }
    docker compose restart frontend
    if($LASTEXITCODE-ne 0){ throw "Frontend restart failed." }

    Start-Sleep -Seconds 5

    Write-Host "[15] Runtime configuration verification"
    docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); assert not hasattr(s,'track_b_competition_mode'); print('competition_mode_attribute=REMOVED'); print('ai_provider=',s.ai_provider); print('ai_fallback_provider=',s.ai_fallback_provider)"
    if($LASTEXITCODE-ne 0){ throw "Runtime verification failed." }

    Write-Host "[16] Service health"
    docker compose ps

    Write-Host "============================================================"
    Write-Host "CLOSED EVIDENCE ARCHITECTURE REMOVAL V2.1 PASS"
    Write-Host "============================================================"
    Write-Host "Closed Evidence Mode: REMOVED"
    Write-Host "Competition-mode configuration: REMOVED"
    Write-Host "Organizer-only acquisition restriction: REMOVED"
    Write-Host "Organizer-only temporal-pair restriction: REMOVED"
    Write-Host "Organizer-only readiness predicates: REMOVED"
    Write-Host "Organizer-only workflow predicates: REMOVED"
    Write-Host "Closed-evidence AI scope rejection: REMOVED"
    Write-Host "Frontend Closed Evidence badge: REMOVED"
    Write-Host "Frontend organizer-only filter: REMOVED"
    Write-Host "Evidence architecture: PROVENANCE CONTROLLED"
    Write-Host "Existing organizer evidence: PRESERVED AS PROVENANCE"
    Write-Host "User/project evidence: ALLOWED"
    Write-Host "Official acquired evidence: ALLOWED BY ARCHITECTURE"
    Write-Host "Server-derived deterministic evidence: ALLOWED"
    Write-Host "Auto Research RT/RSN/RKK/GPP: PRESERVED"
    Write-Host "Terrain auto acquisition + terrain.site_summary: PRESERVED"
    Write-Host "AI provider order: UNCHANGED"
    Write-Host "Anti-hallucination: PRESERVED"
    Write-Host "Numeric grounding: PRESERVED"
    Write-Host "Professional review boundary: PRESERVED"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Next gate: LIVE UI + DOCUMENT EVIDENCE E2E"
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

    if(Test-Path "$Backup\test_controlled_evidence_architecture_v2_1.py"){
        Copy-Item "$Backup\test_controlled_evidence_architecture_v2_1.py" $TestFile -Force
    } else {
        Remove-Item $TestFile -Force -ErrorAction SilentlyContinue
    }

    if(Test-Path "$Backup\.env"){ Copy-Item "$Backup\.env" "$Root\.env" -Force }
    if(Test-Path "$Backup\.env.example"){ Copy-Item "$Backup\.env.example" "$Root\.env.example" -Force }
    throw
}
