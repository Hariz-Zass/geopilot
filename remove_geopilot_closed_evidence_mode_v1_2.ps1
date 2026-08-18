$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Config="$Root\backend\app\core\config.py"
$TrackB="$Root\backend\app\services\track_b.py"
$Acceptance="$Root\backend\app\services\track_b_acceptance.py"
$AI="$Root\backend\app\services\track_b_ai.py"
$Workflow="$Root\backend\app\services\track_b_workflow.py"
$Frontend="$Root\frontend\src\pages\TrackBWorkspacePage.tsx"

$Targets=@($Config,$TrackB,$Acceptance,$AI,$Workflow,$Frontend)
foreach($P in $Targets){ if(!(Test-Path $P)){ throw "Missing source file: $P" } }

Write-Host "============================================================"
Write-Host "GeoPilot Closed Evidence Mode Removal V1.2"
Write-Host "SELF-CONTAINED - NO HELPER FILES REQUIRED"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\closed_evidence_mode_removal_v1_2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null

Copy-Item $Config "$Backup\config.py"
Copy-Item $TrackB "$Backup\track_b.py"
Copy-Item $Acceptance "$Backup\track_b_acceptance.py"
Copy-Item $AI "$Backup\track_b_ai.py"
Copy-Item $Workflow "$Backup\track_b_workflow.py"
Copy-Item $Frontend "$Backup\TrackBWorkspacePage.tsx"
if(Test-Path "$Root\.env"){ Copy-Item "$Root\.env" "$Backup\.env" }
if(Test-Path "$Root\.env.example"){ Copy-Item "$Root\.env.example" "$Backup\.env.example" }

Write-Host "BACKUP: $Backup"

try {
    Write-Host "[1] Remove TRACK_B_COMPETITION_MODE from backend config"
    $t=Get-Content $Config -Raw
    $t=[regex]::Replace(
        $t,
        '(?m)^\s*track_b_competition_mode:\s*bool\s*=\s*Field\([^\r\n]*alias="TRACK_B_COMPETITION_MODE"[^\r\n]*\)\s*\r?\n',
        ''
    )
    Set-Content -Path $Config -Value $t -Encoding UTF8

    Write-Host "[2] Remove organizer-only external acquisition enforcement"
    $t=Get-Content $TrackB -Raw
    $pattern='(?ms)^def _assert_competition_upload\(source_kind: str = "upload"\) -> None:\r?\n.*?(?=^def |\Z)'
    if([regex]::IsMatch($t,$pattern)){
        $replacement=@'
def _assert_competition_upload(source_kind: str = "upload") -> None:
    """Compatibility no-op. Closed Evidence Mode has been removed."""
    return None


'@
        $t=[regex]::Replace($t,$pattern,$replacement,1)
    } elseif($t -match 'Track B competition mode accepts organizer-supplied uploads only'){
        throw "Competition upload restriction found but function boundary could not be patched safely."
    }
    $t=$t.Replace('Closed-evidence declaration','Evidence provenance declaration')
    $t=$t.Replace(
        'This analysis is configured for PLAN-Ai Hackathon 2026 Track B closed-evidence operation. Spatial measurements are derived from organizer-supplied raster evidence. GeoPilot is decision support and does not issue statutory approval or certification.',
        'This analysis uses evidence with recorded provenance. Spatial measurements retain their source lineage, and planning-document evidence may be incorporated through approved GeoPilot retrieval workflows. GeoPilot is decision support and does not issue statutory approval or certification.'
    )
    Set-Content -Path $TrackB -Value $t -Encoding UTF8

    Write-Host "[3] Remove closed-evidence acceptance blocker"
    $t=Get-Content $Acceptance -Raw
    $pattern='(?ms)\s*checks\.append\(\{\s*"key": "competition_mode".*?\}\)\s*if not settings\.track_b_competition_mode:\s*blockers\.append\("Enable TRACK_B_COMPETITION_MODE before competition use\."\)\s*'
    $t=[regex]::Replace($t,$pattern,"`r`n",1)
    $t=$t.Replace(
        'Organizer-only before/after pair is locally available, lineage-verified, and analysis-compatible.',
        'Before/after raster pair is locally available, lineage-verified, and analysis-compatible.'
    )
    $t=$t.Replace(
        'Run the full Track B mission and verify AI outputs against the organizer evidence before presentation.',
        'Run the full Track B mission and verify AI outputs against their cited evidence before presentation.'
    )
    Set-Content -Path $Acceptance -Value $t -Encoding UTF8

    Write-Host "[4] Remove closed-evidence AI scope rejection and prompt wording"
    $t=Get-Content $AI -Raw

    $guard='(?ms)\s*if not evidence or any\(e\.get\("scope"\) not in \{"organizer_supplied_only", "server_owned"\} for e in evidence\):\s*raise TrackBAIError\("[^"]*closed Track B evidence boundary\."\)'
    $t=[regex]::Replace(
        $t,
        $guard,
        "`r`n    if not evidence:`r`n        raise TrackBAIError(`"Track B analysis has no evidence payload.`")"
    )

    $t=$t.Replace('closed-evidence planning decision packet','grounded planning decision packet')
    $t=$t.Replace('CLOSED-EVIDENCE TRACK B FACTS:','GROUNDED TRACK B FACTS:')
    $t=$t.Replace('CLOSED-EVIDENCE URBAN/RURAL FACTS:','GROUNDED URBAN/RURAL FACTS:')
    $t=$t.Replace('CLOSED-EVIDENCE TRACK B DECISION FACTS:','GROUNDED TRACK B DECISION FACTS:')
    $t=$t.Replace(
        'Convert ONLY the supplied organizer-derived deterministic evidence into an auditable planner decision brief.',
        'Convert the supplied grounded evidence into an auditable planner decision brief. Use only evidence present in the request context; do not invent unsupported facts.'
    )
    $t=$t.Replace(
        'Compare ONLY the supplied organizer-derived urban and rural temporal evidence.',
        'Compare the supplied grounded urban and rural temporal evidence.'
    )
    $t=$t.Replace(
        'Interpret ONLY the supplied deterministic facts.',
        'Interpret the supplied grounded facts only.'
    )
    Set-Content -Path $AI -Value $t -Encoding UTF8

    Write-Host "[5] Remove organizer-only workflow wording"
    $t=Get-Content $Workflow -Raw
    $t=$t.Replace(
        'Grounded AI output generated inside the organizer-only evidence boundary.',
        'Grounded AI output generated from evidence with recorded provenance.'
    )
    Set-Content -Path $Workflow -Value $t -Encoding UTF8

    Write-Host "[6] Remove Closed Evidence Mode from frontend"
    $t=Get-Content $Frontend -Raw
    $t=$t.Replace(
        '// temporal question -> Track B closed-evidence decision flow',
        '// temporal question -> Track B grounded decision flow'
    )
    $badge='<div className="evidence-lock"><span className="pulse-dot" /> CLOSED EVIDENCE MODE<br /><small>Organizer data only · external acquisition disabled</small></div>'
    $t=$t.Replace($badge,'')
    $t=$t.Replace('<code>ORGANIZER_ONLY</code>','<code>GROUNDED_EVIDENCE</code>')
    $t=$t.Replace(
        'Register matching organizer-only Urban and Rural T1/T2 pairs with the same Site and data stage.',
        'Register matching Urban and Rural T1/T2 pairs with the same Site and data stage.'
    )
    $t=$t.Replace(
        'GeoPilot automatically selects organizer-only before/after pairs for both challenge contexts, runs deterministic temporal analysis, grounded AI interpretation, planner decision briefs, and strategic comparison.',
        'GeoPilot automatically selects available before/after pairs for both challenge contexts, runs deterministic temporal analysis, grounded AI interpretation, planner decision briefs, and strategic comparison.'
    )
    Set-Content -Path $Frontend -Value $t -Encoding UTF8

    Write-Host "[7] Remove environment variable"
    foreach($EnvPath in @("$Root\.env","$Root\.env.example")){
        if(Test-Path $EnvPath){
            $t=Get-Content $EnvPath -Raw
            $t=[regex]::Replace($t,'(?m)^\s*TRACK_B_COMPETITION_MODE\s*=.*(?:\r?\n|$)','')
            Set-Content -Path $EnvPath -Value $t -Encoding UTF8
            Write-Host "cleaned: $EnvPath"
        }
    }

    Write-Host "[8] Source-level removal audit"
    $sourceFiles=@($Config,$TrackB,$Acceptance,$AI,$Workflow,$Frontend)
    $forbidden=@(
        'CLOSED EVIDENCE MODE',
        'CLOSED-EVIDENCE',
        'closed-evidence',
        'closed Track B evidence boundary',
        'Organizer-only evidence enforcement',
        'external acquisition is disabled',
        'TRACK_B_COMPETITION_MODE'
    )
    foreach($P in $sourceFiles){
        $body=Get-Content $P -Raw
        foreach($needle in $forbidden){
            if($body -match [regex]::Escape($needle)){
                throw "Closed Evidence marker remains in $P : $needle"
            }
        }
    }
    Write-Host "closed_evidence_source_markers=NONE"

    Write-Host "[9] Verify grounding safeguards remain"
    $aiText=Get-Content $AI -Raw
    if($aiText -notmatch 'Never invent'){ throw "Anti-hallucination instruction was lost." }
    if($aiText -notmatch 'NUMERIC GROUNDING RULE'){ throw "Numeric grounding instruction was lost." }
    Write-Host "anti_hallucination=PASS"
    Write-Host "numeric_grounding=PASS"

    Write-Host "[10] Backend syntax checks"
    docker compose exec -T backend python -m py_compile app/core/config.py app/services/track_b.py app/services/track_b_acceptance.py app/services/track_b_ai.py app/services/track_b_workflow.py
    if($LASTEXITCODE-ne 0){ throw "Backend syntax check failed." }

    Write-Host "[11] Frontend production build"
    docker compose exec -T frontend npm run build
    if($LASTEXITCODE-ne 0){ throw "Frontend production build failed." }

    Write-Host "[12] Preserve planning document research regressions"
    foreach($T in @(
        "tests/test_planning_document_auto_research.py",
        "tests/test_document_retrieval.py",
        "tests/test_planning_document_acquisition.py"
    )){
        if(Test-Path "$Root\backend\$T"){
            docker compose exec -T backend python -m pytest -q $T
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $T" }
        }
    }

    Write-Host "[13] Verify effective runtime config imports without competition-mode field"
    docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); assert not hasattr(s,'track_b_competition_mode'); print('track_b_competition_mode_attribute=REMOVED')"
    if($LASTEXITCODE-ne 0){ throw "Runtime config verification failed." }

    Write-Host "[14] Recreate backend and restart frontend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }
    docker compose restart frontend
    if($LASTEXITCODE-ne 0){ throw "Frontend restart failed." }

    Start-Sleep -Seconds 5
    Write-Host "[15] Service health"
    docker compose ps

    Write-Host "============================================================"
    Write-Host "CLOSED EVIDENCE MODE REMOVAL V1.2 PASS"
    Write-Host "============================================================"
    Write-Host "Closed Evidence Mode: REMOVED FROM SYSTEM"
    Write-Host "TRACK_B_COMPETITION_MODE setting: REMOVED"
    Write-Host "Organizer-only acquisition restriction: REMOVED"
    Write-Host "Closed-evidence AI scope gate: REMOVED"
    Write-Host "Closed-evidence AI prompt wording: REMOVED"
    Write-Host "Closed-evidence acceptance requirement: REMOVED"
    Write-Host "Closed-evidence frontend badge: REMOVED"
    Write-Host "Organizer-only frontend wording: REMOVED"
    Write-Host "Auto Research RT/RSN/RKK/GPP: PRESERVED"
    Write-Host "Anti-hallucination: PRESERVED"
    Write-Host "Numeric grounding: PRESERVED"
    Write-Host "Evidence provenance: PRESERVED"
    Write-Host "Professional review boundary: PRESERVED"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "============================================================"
}
catch {
    Write-Host "REMOVAL FAILED - restoring backup."
    Copy-Item "$Backup\config.py" $Config -Force
    Copy-Item "$Backup\track_b.py" $TrackB -Force
    Copy-Item "$Backup\track_b_acceptance.py" $Acceptance -Force
    Copy-Item "$Backup\track_b_ai.py" $AI -Force
    Copy-Item "$Backup\track_b_workflow.py" $Workflow -Force
    Copy-Item "$Backup\TrackBWorkspacePage.tsx" $Frontend -Force
    if(Test-Path "$Backup\.env"){ Copy-Item "$Backup\.env" "$Root\.env" -Force }
    if(Test-Path "$Backup\.env.example"){ Copy-Item "$Backup\.env.example" "$Root\.env.example" -Force }
    throw
}
