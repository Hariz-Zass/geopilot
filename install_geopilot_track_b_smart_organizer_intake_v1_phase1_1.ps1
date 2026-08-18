$ErrorActionPreference = "Stop"
Write-Host "============================================================"
Write-Host "GeoPilot Track B Smart Organizer Intake V1 - Phase 1.1"
Write-Host "Inspect-only / NO DB WRITE / NO MIGRATION"
Write-Host "============================================================"

$root=(Get-Location).Path
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root "artifacts\smart_organizer_intake_v1_phase1_1_backup_$stamp"
$api=Join-Path $root "backend\app\api\v1\track_b.py"
$service=Join-Path $root "backend\app\services\track_b_smart_intake.py"
$test=Join-Path $root "backend\tests\test_track_b_smart_organizer_intake_v1.py"
$client=Join-Path $root "frontend\src\lib\api\trackB.ts"
$page=Join-Path $root "frontend\src\pages\TrackBWorkspacePage.tsx"
$css=Join-Path $root "frontend\src\styles.css"

foreach($p in @($api,$client,$page,$css)){if(-not(Test-Path $p)){throw "Missing: $p"}}
New-Item -ItemType Directory -Force $backup|Out-Null
Copy-Item $api (Join-Path $backup "track_b.py")
Copy-Item $client (Join-Path $backup "trackB.ts")
Copy-Item $page (Join-Path $backup "TrackBWorkspacePage.tsx")
Copy-Item $css (Join-Path $backup "styles.css")
if(Test-Path $service){Copy-Item $service (Join-Path $backup "track_b_smart_intake.py")}
if(Test-Path $test){Copy-Item $test (Join-Path $backup "test_track_b_smart_organizer_intake_v1.py")}
Write-Host "BACKUP: $backup"

function Restore {
 Copy-Item (Join-Path $backup "track_b.py") $api -Force
 Copy-Item (Join-Path $backup "trackB.ts") $client -Force
 Copy-Item (Join-Path $backup "TrackBWorkspacePage.tsx") $page -Force
 Copy-Item (Join-Path $backup "styles.css") $css -Force
 if(Test-Path (Join-Path $backup "track_b_smart_intake.py")){Copy-Item (Join-Path $backup "track_b_smart_intake.py") $service -Force}else{Remove-Item $service -Force -ErrorAction SilentlyContinue}
 if(Test-Path (Join-Path $backup "test_track_b_smart_organizer_intake_v1.py")){Copy-Item (Join-Path $backup "test_track_b_smart_organizer_intake_v1.py") $test -Force}else{Remove-Item $test -Force -ErrorAction SilentlyContinue}
}

try{
 Write-Host "[0] Preflight"
 $a=Get-Content $api -Raw; $c=Get-Content $client -Raw; $p=Get-Content $page -Raw
 if($a.Contains("SMART_ORGANIZER_INTAKE_V1")){throw "Marker already present; stop."}
 if(-not $a.Contains("from app.services.track_b_workflow import run_track_b_hackathon_workflow")){throw "API anchor missing."}
 if(-not $c.Contains("export const trackBApi = {")){throw "Frontend API anchor missing."}
 if(-not $p.Contains('const [ingestMode, setIngestMode] = useState<"processed" | "bundle" | "sentinel">("processed");')){throw "Workspace state anchor missing."}
 Write-Host "preflight_state=CONFIRMED"

 Write-Host "[1] Install backend service + test"
 $svc=Get-Content (Join-Path $root "_smart_intake_service_payload.py.txt") -Raw
 Set-Content $service $svc -Encoding UTF8
 $tst=Get-Content (Join-Path $root "_smart_intake_test_payload.py.txt") -Raw
 Set-Content $test $tst -Encoding UTF8

 Write-Host "[2] Patch Track B API"
 $a=Get-Content $api -Raw
 $a=$a.Replace("from app.services.track_b_workflow import run_track_b_hackathon_workflow","from app.services.track_b_workflow import run_track_b_hackathon_workflow`r`nfrom app.services.track_b_smart_intake import inspect_organizer_package")
 $anchor='@router.post("/workflow/hackathon-run", response_model=TrackBWorkflowResponse)'
 $block=@'
# SMART_ORGANIZER_INTAKE_V1
@router.post("/organizer-intake/inspect")
async def organizer_intake_inspect(
    project_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        return await inspect_organizer_package(files)
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc


@router.post("/workflow/hackathon-run", response_model=TrackBWorkflowResponse)
'@
 if(-not $a.Contains($anchor)){throw "Route anchor missing."}
 $a=$a.Replace($anchor,$block)
 Set-Content $api $a -Encoding UTF8

 Write-Host "[3] Patch frontend API"
 $c=Get-Content $client -Raw
 $types=@'
export type TrackBOrganizerIntakeItem = {
  index:number; filename:string; extension:string; content_type:string|null; size_bytes:number;
  classification:string; confidence:"high"|"moderate"|"low"; location_type:"urban"|"rural"|null;
  temporal_role:"before"|"after"|"reference"|null; data_stage:"raw"|"processed"|null; band_name:string|null;
  acquisition_datetime:string|null; suggested_applicability_role:"zoning"|"land_use"|"planning_block"|"planning_subzone"|null;
  requires_confirmation:boolean; metadata:Record<string,unknown>; issues:string[];
};
export type TrackBOrganizerIntakeReport = {
  phase:"inspect_only"; database_writes:false; file_count:number; supported_or_reviewable_count:number;
  requires_confirmation_count:number; blocker_count:number; class_counts:Record<string,number>;
  blockers:string[]; items:TrackBOrganizerIntakeItem[]; next_action:string;
};

export type TrackBDataset = {
'@
 if(-not $c.Contains("export type TrackBDataset = {")){throw "Type anchor missing."}
 $c=$c.Replace("export type TrackBDataset = {",$types)
 $apiObj=@'
export const trackBApi = {
  // SMART_ORGANIZER_INTAKE_V1
  inspectOrganizerPackage: (projectId:string, files:File[], token:string) => {
    const form=new FormData(); files.forEach((file)=>form.append("files",file));
    return apiClient.request<TrackBOrganizerIntakeReport>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/track-b/organizer-intake/inspect`,
      {method:"POST",headers:auth(token),body:form},
    );
  },

'@
 $c=$c.Replace("export const trackBApi = {",$apiObj)
 Set-Content $client $c -Encoding UTF8

 Write-Host "[4] Patch Track B Workspace"
 $p=Get-Content $page -Raw
 $old='import { trackBApi, type TrackBAIInterpretation, type TrackBAnalysis, type TrackBDataset, type TrackBPlannerDecision, type TrackBWorkflow, type TrackBReadiness } from "../lib/api/trackB";'
 $new='import { trackBApi, type TrackBAIInterpretation, type TrackBAnalysis, type TrackBDataset, type TrackBOrganizerIntakeReport, type TrackBPlannerDecision, type TrackBWorkflow, type TrackBReadiness } from "../lib/api/trackB";'
 if(-not $p.Contains($old)){throw "Import anchor missing."}; $p=$p.Replace($old,$new)
 $state='  const [ingestMode, setIngestMode] = useState<"processed" | "bundle" | "sentinel">("processed");'
 $stateNew=$state+"`r`n  // SMART_ORGANIZER_INTAKE_V1`r`n  const [intakeReport, setIntakeReport] = useState<TrackBOrganizerIntakeReport>();`r`n  const [intakeBusy, setIntakeBusy] = useState(false);"
 $p=$p.Replace($state,$stateNew)
 $fn='  async function upload(event: FormEvent<HTMLFormElement>) {'
 $fnBlock=@'
  // SMART_ORGANIZER_INTAKE_V1
  async function inspectOrganizerPackage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId || !token) { setError("Authentication is required."); return; }
    const form=new FormData(event.currentTarget);
    const files=form.getAll("organizer_files").filter((v):v is File=>v instanceof File && v.size>0);
    if (!files.length) { setError("Choose one or more organizer files."); return; }
    setIntakeBusy(true); setError(undefined);
    try { setIntakeReport(await trackBApi.inspectOrganizerPackage(projectId,files,token)); }
    catch(caught){ setError(caught instanceof ApiError ? caught.message : caught instanceof Error ? caught.message : "Organizer inspection failed."); }
    finally { setIntakeBusy(false); }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
'@
 if(-not $p.Contains($fn)){throw "Upload function anchor missing."}; $p=$p.Replace($fn,$fnBlock)

 $ui='<form className="trackb-form" onSubmit={upload}>'
 $smart=@'
<section className="smart-intake">
  <div className="smart-intake-head"><div><span>SMART ORGANIZER INTAKE</span><strong>Inspect all challenge materials at once</strong><small>Inspect-only. No database writes until confirmation.</small></div><code>PHASE 1</code></div>
  <form className="smart-intake-form" onSubmit={inspectOrganizerPackage}>
    <label>Organizer files<input name="organizer_files" type="file" multiple accept=".tif,.tiff,.jp2,.zip,.geojson,.json,.pdf,.csv" required /></label>
    <button className="neon-button" disabled={intakeBusy}>{intakeBusy ? "Inspecting…" : "Inspect & classify package"}</button>
  </form>
  {intakeReport && <div className="smart-intake-report">
    <div className="smart-intake-summary"><span><strong>{intakeReport.file_count}</strong> files</span><span><strong>{intakeReport.supported_or_reviewable_count}</strong> recognized</span><span><strong>{intakeReport.requires_confirmation_count}</strong> confirm</span><span><strong>{intakeReport.blocker_count}</strong> blockers</span></div>
    <p>{intakeReport.next_action}</p>
    <div className="smart-intake-items">{intakeReport.items.map((item)=><article key={`${item.index}-${item.filename}`}><div><strong>{item.filename}</strong><small>{item.classification.replaceAll("_"," ")}</small></div><div className="smart-intake-tags"><code>{item.confidence.toUpperCase()}</code>{item.location_type&&<code>{item.location_type.toUpperCase()}</code>}{item.temporal_role&&<code>{item.temporal_role.toUpperCase()}</code>}{item.data_stage&&<code>{item.data_stage.toUpperCase()}</code>}{item.band_name&&<code>{item.band_name}</code>}{item.suggested_applicability_role&&<code>{item.suggested_applicability_role.toUpperCase()}</code>}{item.requires_confirmation&&<code className="confirm">CONFIRM</code>}</div>{!!item.issues.length&&<ul>{item.issues.map((issue)=><li key={issue}>{issue}</li>)}</ul>}</article>)}</div>
  </div>}
</section>
<div className="manual-ingestion-label"><span>MANUAL / FALLBACK INGESTION</span><small>Existing path preserved.</small></div>
<form className="trackb-form" onSubmit={upload}>
'@
 $idx=$p.IndexOf($ui)
 if($idx -lt 0){throw "Manual form anchor missing."}
 $p=$p.Remove($idx,$ui.Length).Insert($idx,$smart)
 Set-Content $page $p -Encoding UTF8

 Write-Host "[5] Add CSS"
 @'

/* SMART_ORGANIZER_INTAKE_V1 */
.smart-intake{display:grid;gap:.75rem;padding:.85rem;margin:0 0 1rem;border:1px solid rgba(88,245,223,.22);border-radius:14px;background:linear-gradient(145deg,rgba(16,42,58,.78),rgba(7,24,39,.86))}
.smart-intake-head{display:flex;justify-content:space-between;gap:.7rem;align-items:flex-start}.smart-intake-head>div{display:grid;gap:.2rem}
.smart-intake-head span,.manual-ingestion-label span{font-size:.62rem;letter-spacing:.13em;color:var(--tb-cyan);font-weight:900}
.smart-intake-head small,.manual-ingestion-label small,.smart-intake-report>p{color:var(--tb-muted);line-height:1.4}
.smart-intake-head>code{font-size:.58rem;border:1px solid rgba(88,245,223,.22);border-radius:999px;padding:.28rem .45rem;color:var(--tb-cyan)}
.smart-intake-form{display:grid;gap:.55rem}.smart-intake-form label{display:grid;gap:.35rem;font-size:.68rem;text-transform:uppercase;color:var(--tb-muted);font-weight:800}
.smart-intake-report{display:grid;gap:.6rem}.smart-intake-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:.4rem}
.smart-intake-summary span{display:grid;padding:.45rem;border:1px solid var(--tb-line);border-radius:10px;font-size:.58rem;text-transform:uppercase;color:var(--tb-muted)}.smart-intake-summary strong{font-size:.9rem;color:#fff}
.smart-intake-items{display:grid;gap:.45rem;max-height:390px;overflow:auto}.smart-intake-items article{display:grid;gap:.38rem;padding:.55rem;border:1px solid var(--tb-line);border-radius:11px;background:rgba(1,10,18,.45)}
.smart-intake-items article>div:first-child{display:grid}.smart-intake-items article strong{font-size:.72rem;overflow-wrap:anywhere}.smart-intake-items article small{font-size:.58rem;text-transform:uppercase;color:var(--tb-muted)}
.smart-intake-items ul{margin:.1rem 0 0;padding-left:1rem;color:var(--tb-muted);font-size:.62rem}.smart-intake-tags{display:flex;gap:.25rem;flex-wrap:wrap}
.smart-intake-tags code{font-size:.52rem;padding:.2rem .32rem;border-radius:6px;border:1px solid rgba(95,220,255,.18);color:#b8dcea}.smart-intake-tags code.confirm{color:#ffc65d}
.manual-ingestion-label{display:grid;gap:.12rem;margin:.2rem 0 .65rem}@media(max-width:980px){.smart-intake-summary{grid-template-columns:repeat(2,1fr)}}
'@ | Add-Content $css -Encoding UTF8

 Write-Host "[6] Syntax + focused tests"
 docker compose exec -T backend python -m py_compile /app/app/services/track_b_smart_intake.py /app/app/api/v1/track_b.py
 if($LASTEXITCODE-ne 0){throw "Backend syntax failed."}
 docker compose exec -T backend python -m pytest -q tests/test_track_b_smart_organizer_intake_v1.py
 if($LASTEXITCODE-ne 0){throw "Focused regression failed."}

 Write-Host "[7] Track B regression"
 docker compose exec -T backend sh -lc "python -m pytest -q `$(find tests -maxdepth 1 -type f \( -name '*track*b*.py' -o -name '*track_b*.py' \) ! -name 'test_track_b_smart_organizer_intake_v1.py' | sort | tr '\n' ' ')"
 if($LASTEXITCODE-ne 0){throw "Track B regression failed."}

 Write-Host "[8] Frontend typecheck + build"
 docker compose exec -T frontend npm run typecheck
 if($LASTEXITCODE-ne 0){throw "Frontend typecheck failed."}
 docker compose exec -T frontend npm run build
 if($LASTEXITCODE-ne 0){throw "Frontend build failed."}

 Write-Host "[9] Full backend regression"
 docker compose exec -T backend python -m pytest -q
 if($LASTEXITCODE-ne 0){throw "Full regression failed."}

 Write-Host "[10] Recreate runtime"
 docker compose up -d --force-recreate backend frontend
 if($LASTEXITCODE-ne 0){throw "Recreate failed."}
 Start-Sleep -Seconds 8
 docker compose ps

 Write-Host "[11] Runtime verification"
 docker compose exec -T backend python -c "from app.services.track_b_smart_intake import inspect_organizer_package; from pathlib import Path; t=Path('/app/app/api/v1/track_b.py').read_text(); assert '/organizer-intake/inspect' in t; print('runtime_smart_intake_phase1=PASS')"
 if($LASTEXITCODE-ne 0){throw "Runtime verification failed."}

 Remove-Item (Join-Path $root "_smart_intake_service_payload.py.txt") -Force -ErrorAction SilentlyContinue
 Remove-Item (Join-Path $root "_smart_intake_test_payload.py.txt") -Force -ErrorAction SilentlyContinue
 Write-Host "============================================================"
 Write-Host "TRACK B SMART ORGANIZER INTAKE V1 - PHASE 1.1 PASS"
 Write-Host "============================================================"
 Write-Host "Inspect/classify multi-file package: ENABLED"
 Write-Host "Inspection DB writes: NONE"
 Write-Host "Manual ingestion: PRESERVED"
 Write-Host "Migration: NONE"
 Write-Host "Next gate: LIVE SMART INTAKE INSPECTION"
}catch{
 Write-Host ""
 Write-Host "INSTALL FAILED - restoring backup."
 Restore
 throw
}
