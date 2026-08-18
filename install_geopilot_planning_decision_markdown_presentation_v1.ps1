$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Page="$Root\frontend\src\pages\TrackBWorkspacePage.tsx"
$Css="$Root\frontend\src\styles.css"

if(!(Test-Path $Page)){ throw "Missing $Page" }
if(!(Test-Path $Css)){ throw "Missing $Css" }

Write-Host "============================================================"
Write-Host "GeoPilot Planning Decision Markdown Presentation V1"
Write-Host "FRONTEND ONLY - NO BACKEND / DB / MIGRATION"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\planning_decision_markdown_presentation_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Page "$Backup\TrackBWorkspacePage.tsx"
Copy-Item $Css "$Backup\styles.css"
Write-Host "BACKUP: $Backup"

try {
  Write-Host "[0] Preflight"
  $page=Get-Content $Page -Raw
  $pkg=Get-Content "$Root\frontend\package.json" -Raw
  if($page -notmatch '<p>\{decision\.planning_implication\}</p>'){ throw "Raw planning implication renderer not found." }
  if($page -notmatch '<p>\{decision\.evidence_summary\}</p>'){ throw "Raw evidence summary renderer not found." }
  if($pkg -notmatch '"react-markdown"'){ throw "react-markdown missing." }
  if($pkg -notmatch '"remark-gfm"'){ throw "remark-gfm missing." }
  Write-Host "preflight_state=CONFIRMED"

  Write-Host "[1] Patch page"
  $Patch="$Root\frontend\_patch_markdown_presentation_v1.py"
  @'
from pathlib import Path

p=Path("/app/src/pages/TrackBWorkspacePage.tsx")
t=p.read_text(encoding="utf-8-sig")

route_import='import { Link, Navigate, useParams } from "react-router-dom";\n'
if 'import ReactMarkdown from "react-markdown";' not in t:
    if route_import not in t:
        raise SystemExit("IMPORT_ANCHOR_NOT_FOUND")
    t=t.replace(route_import, route_import+'import ReactMarkdown from "react-markdown";\nimport remarkGfm from "remark-gfm";\n',1)

label_block='function label(value: unknown) {\n  return typeof value === "string" ? value : "—";\n}\n\n'
helper='function GroundedMarkdown({ value }: { value: string }) {\n  return (\n    <div className="grounded-markdown">\n      <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>\n    </div>\n  );\n}\n\n'
if 'function GroundedMarkdown(' not in t:
    if label_block not in t:
        raise SystemExit("LABEL_ANCHOR_NOT_FOUND")
    t=t.replace(label_block,label_block+helper,1)

old_core='<article className="decision-core"><small>PLANNER ISSUE</small><h3>{decision.decision_title}</h3><p>{decision.issue}</p><small>PLANNING IMPLICATION</small><p>{decision.planning_implication}</p></article>'
new_core='<article className="decision-core"><small>PLANNER ISSUE</small><h3>{decision.decision_title}</h3><GroundedMarkdown value={decision.issue} /><small>PLANNING IMPLICATION</small><GroundedMarkdown value={decision.planning_implication} /></article>'
if old_core not in t:
    raise SystemExit("DECISION_CORE_PATTERN_NOT_FOUND")
t=t.replace(old_core,new_core,1)

old_ev='<article className="decision-evidence"><small>EVIDENCE SUMMARY</small><p>{decision.evidence_summary}</p><div className="ai-evidence-tags">{decision.evidence_refs.map((ref) => <code key={ref}>{ref}</code>)}</div></article>'
new_ev='<article className="decision-evidence"><small>EVIDENCE SUMMARY</small><GroundedMarkdown value={decision.evidence_summary} /><div className="ai-evidence-tags">{decision.evidence_refs.map((ref) => <code key={ref}>{ref}</code>)}</div></article>'
if old_ev not in t:
    raise SystemExit("DECISION_EVIDENCE_PATTERN_NOT_FOUND")
t=t.replace(old_ev,new_ev,1)

p.write_text(t,encoding="utf-8")
print("PATCHED:",p)
'@ | Set-Content $Patch -Encoding UTF8

  try {
    docker compose exec -T frontend python /app/_patch_markdown_presentation_v1.py
    if($LASTEXITCODE-ne 0){ throw "Page patch failed." }
  } finally {
    Remove-Item $Patch -Force -ErrorAction SilentlyContinue
  }

  Write-Host "[2] Add scoped CSS"
  $css=Get-Content $Css -Raw
  if($css -notmatch 'PLANNING_DECISION_MARKDOWN_PRESENTATION_V1'){
@'

/* PLANNING_DECISION_MARKDOWN_PRESENTATION_V1 */
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
'@ | Add-Content $Css
  }

  Write-Host "[3] Static verification"
  $page=Get-Content $Page -Raw
  if($page -notmatch 'import ReactMarkdown from "react-markdown";'){ throw "ReactMarkdown import missing." }
  if($page -notmatch 'import remarkGfm from "remark-gfm";'){ throw "remarkGfm import missing." }
  if($page -notmatch 'function GroundedMarkdown'){ throw "GroundedMarkdown helper missing." }
  if($page -match '<p>\{decision\.planning_implication\}</p>'){ throw "Raw planning implication remains." }
  if($page -match '<p>\{decision\.evidence_summary\}</p>'){ throw "Raw evidence summary remains." }
  if($page -match 'dangerouslySetInnerHTML'){ throw "Unsafe HTML renderer detected." }
  Write-Host "static_renderer_contract=PASS"

  Write-Host "[4] Typecheck"
  docker compose exec -T frontend npm run typecheck
  if($LASTEXITCODE-ne 0){ throw "Frontend typecheck failed." }

  Write-Host "[5] Production build"
  docker compose exec -T frontend npm run build
  if($LASTEXITCODE-ne 0){ throw "Frontend build failed." }

  Write-Host "[6] Restart frontend"
  docker compose restart frontend
  if($LASTEXITCODE-ne 0){ throw "Frontend restart failed." }
  Start-Sleep -Seconds 3

  Write-Host "[7] Frontend health"
  docker compose ps frontend

  Write-Host "============================================================"
  Write-Host "PLANNING DECISION MARKDOWN PRESENTATION V1 PASS"
  Write-Host "============================================================"
  Write-Host "Planning implication markdown: RENDERED"
  Write-Host "Evidence summary markdown: RENDERED"
  Write-Host "Headings/bold/lists/tables: SUPPORTED"
  Write-Host "GFM table rendering: ENABLED"
  Write-Host "Long-content wrapping: IMPROVED"
  Write-Host "dangerouslySetInnerHTML: NOT USED"
  Write-Host "Answer/evidence content: UNCHANGED"
  Write-Host "Auto Research: UNCHANGED"
  Write-Host "Backend change: NONE"
  Write-Host "DB schema change: NONE"
  Write-Host "Migration: NONE"
  Write-Host "Next gate: CTRL+F5 + RETEST GPP PRESENTATION"
  Write-Host "============================================================"
}
catch {
  Write-Host "INSTALL FAILED - restoring frontend backup."
  Copy-Item "$Backup\TrackBWorkspacePage.tsx" $Page -Force
  Copy-Item "$Backup\styles.css" $Css -Force
  throw
}
