$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$PagePath="$Root\frontend\src\pages\TrackBWorkspacePage.tsx"
$CssPath="$Root\frontend\src\styles.css"
$PackagePath="$Root\frontend\package.json"

foreach($P in @($PagePath,$CssPath,$PackagePath)){
    if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Planning Decision Markdown Presentation V1.1"
Write-Host "Host-side recovery: frontend container has no Python"
Write-Host "Fix PowerShell case-insensitive variable collision"
Write-Host "FRONTEND ONLY - NO BACKEND / DB / MIGRATION"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir="$Root\artifacts\planning_decision_markdown_presentation_v1_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
Copy-Item $PagePath "$BackupDir\TrackBWorkspacePage.tsx"
Copy-Item $CssPath "$BackupDir\styles.css"
Write-Host "BACKUP: $BackupDir"

try {
    Write-Host "[0] Confirm V1 did not partially modify production source"
    $PageText=Get-Content $PagePath -Raw
    $CssText=Get-Content $CssPath -Raw
    $PackageText=Get-Content $PackagePath -Raw

    if($PageText -match 'function GroundedMarkdown\(' -or $PageText -match 'import ReactMarkdown from "react-markdown";'){
        throw "Unexpected partial V1 page modification detected. Stop for manual inspection."
    }
    if($CssText -match 'PLANNING_DECISION_MARKDOWN_PRESENTATION_V1'){
        throw "Unexpected partial V1 CSS modification detected. Stop for manual inspection."
    }
    if($PageText -notmatch '<p>\{decision\.planning_implication\}</p>'){
        throw "Expected raw planning_implication renderer not found."
    }
    if($PageText -notmatch '<p>\{decision\.evidence_summary\}</p>'){
        throw "Expected raw evidence_summary renderer not found."
    }
    if($PackageText -notmatch '"react-markdown"'){ throw "react-markdown dependency missing." }
    if($PackageText -notmatch '"remark-gfm"'){ throw "remark-gfm dependency missing." }
    Write-Host "rollback_state=CONFIRMED"

    Write-Host "[1] Apply host-side TSX patch"
    $RouteImport='import { Link, Navigate, useParams } from "react-router-dom";'
    $MarkdownImports=@'
import { Link, Navigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
'@

    if(-not $PageText.Contains($RouteImport)){
        throw "React Router import anchor not found."
    }
    $PageText=$PageText.Replace($RouteImport,$MarkdownImports.TrimEnd())

    $LabelBlock=@'
function label(value: unknown) {
  return typeof value === "string" ? value : "—";
}
'@

    $HelperBlock=@'
function label(value: unknown) {
  return typeof value === "string" ? value : "—";
}

function GroundedMarkdown({ value }: { value: string }) {
  return (
    <div className="grounded-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
    </div>
  );
}
'@

    if(-not $PageText.Contains($LabelBlock.TrimEnd())){
        throw "label() helper anchor not found."
    }
    $PageText=$PageText.Replace($LabelBlock.TrimEnd(),$HelperBlock.TrimEnd())

    $OldCore='<article className="decision-core"><small>PLANNER ISSUE</small><h3>{decision.decision_title}</h3><p>{decision.issue}</p><small>PLANNING IMPLICATION</small><p>{decision.planning_implication}</p></article>'
    $NewCore='<article className="decision-core"><small>PLANNER ISSUE</small><h3>{decision.decision_title}</h3><GroundedMarkdown value={decision.issue} /><small>PLANNING IMPLICATION</small><GroundedMarkdown value={decision.planning_implication} /></article>'
    if(-not $PageText.Contains($OldCore)){ throw "Decision core renderer pattern not found." }
    $PageText=$PageText.Replace($OldCore,$NewCore)

    $OldEvidence='<article className="decision-evidence"><small>EVIDENCE SUMMARY</small><p>{decision.evidence_summary}</p><div className="ai-evidence-tags">{decision.evidence_refs.map((ref) => <code key={ref}>{ref}</code>)}</div></article>'
    $NewEvidence='<article className="decision-evidence"><small>EVIDENCE SUMMARY</small><GroundedMarkdown value={decision.evidence_summary} /><div className="ai-evidence-tags">{decision.evidence_refs.map((ref) => <code key={ref}>{ref}</code>)}</div></article>'
    if(-not $PageText.Contains($OldEvidence)){ throw "Decision evidence renderer pattern not found." }
    $PageText=$PageText.Replace($OldEvidence,$NewEvidence)

    [System.IO.File]::WriteAllText($PagePath,$PageText,[System.Text.UTF8Encoding]::new($false))
    Write-Host "PATCHED: $PagePath"

    Write-Host "[2] Apply scoped host-side CSS"
    $MarkdownCss=@'

/* PLANNING_DECISION_MARKDOWN_PRESENTATION_V1_1 */
.grounded-markdown { color:#9db2c2; font-size:.73rem; line-height:1.58; min-width:0; overflow-wrap:anywhere; }
.grounded-markdown > :first-child { margin-top:.3rem; }
.grounded-markdown > :last-child { margin-bottom:.65rem; }
.grounded-markdown p { margin:.3rem 0 .65rem; color:#9db2c2; font-size:.73rem; line-height:1.58; }
.grounded-markdown h1,.grounded-markdown h2,.grounded-markdown h3,.grounded-markdown h4 { margin:.75rem 0 .38rem; color:#eefcff; line-height:1.25; }
.grounded-markdown h1 { font-size:1.02rem; }
.grounded-markdown h2 { font-size:.94rem; }
.grounded-markdown h3 { font-size:.86rem; }
.grounded-markdown h4 { font-size:.79rem; }
.grounded-markdown strong { color:#f0fbff; font-weight:800; }
.grounded-markdown ul,.grounded-markdown ol { margin:.35rem 0 .7rem; padding-left:1.2rem; color:#9db2c2; }
.grounded-markdown li { margin:.2rem 0; }
.grounded-markdown blockquote { margin:.5rem 0 .7rem; padding:.45rem .7rem; border-left:2px solid rgba(100,232,212,.65); background:rgba(100,232,212,.05); color:#b9cbd8; }
.grounded-markdown code { padding:.08rem .28rem; border-radius:5px; background:rgba(113,168,255,.1); color:#b9f5ec; font-size:.68rem; }
.grounded-markdown pre { max-width:100%; overflow:auto; padding:.65rem; border-radius:8px; background:rgba(2,10,20,.72); }
.grounded-markdown pre code { padding:0; background:transparent; }
.grounded-markdown table { width:100%; border-collapse:collapse; margin:.55rem 0 .8rem; font-size:.69rem; display:block; overflow-x:auto; }
.grounded-markdown thead { background:rgba(100,232,212,.07); }
.grounded-markdown th,.grounded-markdown td { padding:.4rem .48rem; border:1px solid rgba(109,171,206,.18); text-align:left; vertical-align:top; min-width:90px; }
.grounded-markdown th { color:#dffdf8; font-weight:800; }
.grounded-markdown td { color:#9db2c2; }
.grounded-markdown a { color:#71d9ff; text-decoration:underline; text-underline-offset:2px; }
.grounded-markdown hr { border:0; border-top:1px solid rgba(109,171,206,.15); margin:.7rem 0; }
'@

    $CssText=Get-Content $CssPath -Raw
    if($CssText -notmatch 'PLANNING_DECISION_MARKDOWN_PRESENTATION_V1_1'){
        [System.IO.File]::AppendAllText($CssPath,$MarkdownCss,[System.Text.UTF8Encoding]::new($false))
    }
    Write-Host "PATCHED: $CssPath"

    Write-Host "[3] Static source verification"
    $VerifyPage=Get-Content $PagePath -Raw
    $VerifyCss=Get-Content $CssPath -Raw

    if($VerifyPage -notmatch 'import ReactMarkdown from "react-markdown";'){ throw "ReactMarkdown import missing." }
    if($VerifyPage -notmatch 'import remarkGfm from "remark-gfm";'){ throw "remarkGfm import missing." }
    if($VerifyPage -notmatch 'function GroundedMarkdown'){ throw "GroundedMarkdown helper missing." }
    if($VerifyPage -match '<p>\{decision\.planning_implication\}</p>'){ throw "Raw planning implication renderer remains." }
    if($VerifyPage -match '<p>\{decision\.evidence_summary\}</p>'){ throw "Raw evidence summary renderer remains." }
    if($VerifyPage -match 'dangerouslySetInnerHTML'){ throw "Unsafe dangerouslySetInnerHTML found." }
    if($VerifyCss -notmatch 'PLANNING_DECISION_MARKDOWN_PRESENTATION_V1_1'){ throw "Scoped markdown CSS missing." }
    Write-Host "static_renderer_contract=PASS"

    Write-Host "[4] Frontend typecheck"
    docker compose exec -T frontend npm run typecheck
    if($LASTEXITCODE-ne 0){ throw "Frontend typecheck failed." }

    Write-Host "[5] Frontend production build"
    docker compose exec -T frontend npm run build
    if($LASTEXITCODE-ne 0){ throw "Frontend production build failed." }

    Write-Host "[6] Restart frontend"
    docker compose restart frontend
    if($LASTEXITCODE-ne 0){ throw "Frontend restart failed." }

    Start-Sleep -Seconds 3

    Write-Host "[7] Frontend health"
    docker compose ps frontend

    Write-Host "============================================================"
    Write-Host "PLANNING DECISION MARKDOWN PRESENTATION V1.1 PASS"
    Write-Host "============================================================"
    Write-Host "Frontend-container Python dependency: REMOVED"
    Write-Host "PowerShell path/content variable collision: FIXED"
    Write-Host "Planning implication markdown: RENDERED"
    Write-Host "Evidence summary markdown: RENDERED"
    Write-Host "Headings/bold/lists/tables: SUPPORTED"
    Write-Host "GFM tables: ENABLED"
    Write-Host "Long-content wrapping: IMPROVED"
    Write-Host "dangerouslySetInnerHTML: NOT USED"
    Write-Host "Answer/evidence content: UNCHANGED"
    Write-Host "Backend change: NONE"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Next gate: CTRL+F5 + RETEST GPP PRESENTATION"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring frontend backup."
    Copy-Item "$BackupDir\TrackBWorkspacePage.tsx" $PagePath -Force
    Copy-Item "$BackupDir\styles.css" $CssPath -Force
    throw
}
