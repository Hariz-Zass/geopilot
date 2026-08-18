$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Isolation="$Root\backend\app\services\isolation.py"
$PlanningRuns="$Root\backend\app\services\planning_runs.py"
$Orchestrator="$Root\backend\app\services\planning_orchestrator.py"
$TrackBApi="$Root\backend\app\api\v1\track_b.py"
$Test="$Root\backend\tests\test_track_b_planning_site_lifecycle_bridge_v1.py"

foreach($P in @($Isolation,$PlanningRuns,$Orchestrator,$TrackBApi)){
    if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Track B Planning Site Lifecycle Bridge V1"
Write-Host "Inactive-but-unarchived Track B Site -> AVAILABLE analysis scope"
Write-Host "Normal PlanningRun ACTIVE-site requirement remains default"
Write-Host "NO DB DATA UPDATE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\track_b_planning_site_lifecycle_bridge_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null

Copy-Item $Isolation "$Backup\isolation.py"
Copy-Item $PlanningRuns "$Backup\planning_runs.py"
Copy-Item $Orchestrator "$Backup\planning_orchestrator.py"
Copy-Item $TrackBApi "$Backup\track_b_api.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_track_b_planning_site_lifecycle_bridge_v1.py" }

Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Preflight lifecycle mismatch gate"
    $iso=Get-Content $Isolation -Raw
    $runs=Get-Content $PlanningRuns -Raw
    $orch=Get-Content $Orchestrator -Raw
    $api=Get-Content $TrackBApi -Raw

    if($iso -notmatch 'site_state=SiteState\.ACTIVE'){ throw "Expected strict resolve_analysis_scope ACTIVE-site gate not found." }
    if($runs -notmatch 'resolve_analysis_scope\(session,owner=owner,project_id=project_id,site_id=site_id\)'){ throw "Expected PlanningRun strict scope call not found." }
    if($orch -notmatch 'run = get_planning_run\('){ throw "Expected execute_planning_run get_planning_run call not found." }
    if($api -notmatch '_run_track_b_planning_question'){ throw "Track B planning dispatcher V1 is not present." }
    Write-Host "preflight_state=CONFIRMED"

    Write-Host "[1] Patch isolation scope"
    $py=@'
from pathlib import Path
p=Path("/app/app/services/isolation.py")
t=p.read_text(encoding="utf-8-sig")
old="""def resolve_analysis_scope(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> SiteScope:
"""
new="""def resolve_analysis_scope(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> SiteScope:
"""
if old not in t:
    raise SystemExit("RESOLVE_ANALYSIS_SIGNATURE_NOT_FOUND")
t=t.replace(old,new,1)
old2="""        project_state=ProjectState.ACTIVE,
        site_state=SiteState.ACTIVE,
"""
new2="""        project_state=ProjectState.ACTIVE,
        site_state=site_state,
"""
if old2 not in t:
    raise SystemExit("RESOLVE_ANALYSIS_GATE_NOT_FOUND")
t=t.replace(old2,new2,1)
p.write_text(t,encoding="utf-8")
print("PATCHED",p)
'@
    $Tmp="$Root\backend\_patch_iso_lifecycle_v1.py"
    Set-Content $Tmp $py -Encoding UTF8
    try {
        docker compose exec -T backend python /app/_patch_iso_lifecycle_v1.py
        if($LASTEXITCODE-ne 0){ throw "Isolation patch failed." }
    } finally { Remove-Item $Tmp -Force -ErrorAction SilentlyContinue }

    Write-Host "[2] Patch PlanningRun create/get defaults"
    $py=@'
from pathlib import Path
p=Path("/app/app/services/planning_runs.py")
t=p.read_text(encoding="utf-8-sig")
t=t.replace("from app.services.isolation import resolve_analysis_scope","from app.services.isolation import SiteState, resolve_analysis_scope",1)
old="def create_planning_run(session:Session,*,owner:User,project_id:uuid.UUID,site_id:uuid.UUID,request:PlanningRunCreate):\n resolve_analysis_scope(session,owner=owner,project_id=project_id,site_id=site_id)"
new="def create_planning_run(session:Session,*,owner:User,project_id:uuid.UUID,site_id:uuid.UUID,request:PlanningRunCreate,site_state:SiteState=SiteState.ACTIVE):\n resolve_analysis_scope(session,owner=owner,project_id=project_id,site_id=site_id,site_state=site_state)"
if old not in t:
    raise SystemExit("CREATE_PATTERN_NOT_FOUND")
t=t.replace(old,new,1)
old="def get_planning_run(session:Session,*,owner:User,project_id:uuid.UUID,site_id:uuid.UUID,run_id:uuid.UUID):\n resolve_analysis_scope(session,owner=owner,project_id=project_id,site_id=site_id)"
new="def get_planning_run(session:Session,*,owner:User,project_id:uuid.UUID,site_id:uuid.UUID,run_id:uuid.UUID,site_state:SiteState=SiteState.ACTIVE):\n resolve_analysis_scope(session,owner=owner,project_id=project_id,site_id=site_id,site_state=site_state)"
if old not in t:
    raise SystemExit("GET_PATTERN_NOT_FOUND")
t=t.replace(old,new,1)
p.write_text(t,encoding="utf-8")
print("PATCHED",p)
'@
    $Tmp="$Root\backend\_patch_runs_lifecycle_v1.py"
    Set-Content $Tmp $py -Encoding UTF8
    try {
        docker compose exec -T backend python /app/_patch_runs_lifecycle_v1.py
        if($LASTEXITCODE-ne 0){ throw "PlanningRuns patch failed." }
    } finally { Remove-Item $Tmp -Force -ErrorAction SilentlyContinue }

    Write-Host "[3] Patch Planning Orchestrator execute scope"
    $py=@'
from pathlib import Path
p=Path("/app/app/services/planning_orchestrator.py")
t=p.read_text(encoding="utf-8-sig")
if "from app.services.isolation import SiteState" not in t:
    anchor="from app.services.planning_runs import (\n"
    if anchor not in t:
        raise SystemExit("IMPORT_ANCHOR_NOT_FOUND")
    t=t.replace(anchor,"from app.services.isolation import SiteState\n"+anchor,1)
old="""def execute_planning_run(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    run_id: uuid.UUID,
):
"""
new="""def execute_planning_run(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    run_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
):
"""
if old not in t:
    raise SystemExit("EXECUTE_SIGNATURE_NOT_FOUND")
t=t.replace(old,new,1)
start=t.find("    run = get_planning_run(")
if start<0:
    raise SystemExit("GET_CALL_NOT_FOUND")
end=t.find("    )",start)
if end<0:
    raise SystemExit("GET_CALL_END_NOT_FOUND")
seg=t[start:end+5]
if "site_state=" not in seg:
    seg=seg.replace("        run_id=run_id,\n","        run_id=run_id,\n        site_state=site_state,\n",1)
    t=t[:start]+seg+t[end+5:]
p.write_text(t,encoding="utf-8")
print("PATCHED",p)
'@
    $Tmp="$Root\backend\_patch_orch_lifecycle_v1.py"
    Set-Content $Tmp $py -Encoding UTF8
    try {
        docker compose exec -T backend python /app/_patch_orch_lifecycle_v1.py
        if($LASTEXITCODE-ne 0){ throw "Orchestrator patch failed." }
    } finally { Remove-Item $Tmp -Force -ErrorAction SilentlyContinue }

    Write-Host "[4] Opt only Track B document dispatcher into AVAILABLE"
    $py=@'
from pathlib import Path
p=Path("/app/app/api/v1/track_b.py")
t=p.read_text(encoding="utf-8-sig")
if "from app.services.isolation import SiteState" not in t:
    anchor="from app.services.data_requirement_router import route_question\n"
    if anchor not in t:
        raise SystemExit("TRACK_B_IMPORT_ANCHOR_NOT_FOUND")
    t=t.replace(anchor,anchor+"from app.services.isolation import SiteState\n",1)
start=t.find("def _run_track_b_planning_question(")
if start<0:
    raise SystemExit("HELPER_NOT_FOUND")
end=t.find("\n\n@router.post",start)
if end<0:
    raise SystemExit("HELPER_END_NOT_FOUND")
block=t[start:end]
if "site_state=SiteState.AVAILABLE" not in block:
    block=block.replace(
        "        request=PlanningRunCreate(question=question, development_intent=None),\n",
        "        request=PlanningRunCreate(question=question, development_intent=None),\n        site_state=SiteState.AVAILABLE,\n",
        1,
    )
    block=block.replace(
        "        run_id=run.id,\n",
        "        run_id=run.id,\n        site_state=SiteState.AVAILABLE,\n",
        1,
    )
t=t[:start]+block+t[end:]
p.write_text(t,encoding="utf-8")
print("PATCHED",p)
'@
    $Tmp="$Root\backend\_patch_trackb_lifecycle_v1.py"
    Set-Content $Tmp $py -Encoding UTF8
    try {
        docker compose exec -T backend python /app/_patch_trackb_lifecycle_v1.py
        if($LASTEXITCODE-ne 0){ throw "Track B API lifecycle patch failed." }
    } finally { Remove-Item $Tmp -Force -ErrorAction SilentlyContinue }

    Write-Host "[5] Install focused tests"
    $testText=@'
from pathlib import Path
import inspect
from app.services.isolation import SiteState, resolve_analysis_scope
from app.services.planning_runs import create_planning_run, get_planning_run
from app.services.planning_orchestrator import execute_planning_run

def test_defaults_remain_active():
    assert inspect.signature(resolve_analysis_scope).parameters["site_state"].default is SiteState.ACTIVE
    assert inspect.signature(create_planning_run).parameters["site_state"].default is SiteState.ACTIVE
    assert inspect.signature(get_planning_run).parameters["site_state"].default is SiteState.ACTIVE
    assert inspect.signature(execute_planning_run).parameters["site_state"].default is SiteState.ACTIVE

def test_track_b_route_opts_into_available_only():
    text=Path("app/api/v1/track_b.py").read_text(encoding="utf-8-sig")
    start=text.index("def _run_track_b_planning_question(")
    end=text.index("\n\n@router.post",start)
    block=text[start:end]
    assert block.count("site_state=SiteState.AVAILABLE")==2

def test_available_still_rejects_archived_site():
    text=Path("app/services/isolation.py").read_text(encoding="utf-8-sig")
    assert "site_state in {SiteState.AVAILABLE, SiteState.ACTIVE} and site.is_archived" in text
    assert 'raise ScopeStateError("site is archived")' in text

def test_active_still_rejects_inactive_site():
    text=Path("app/services/isolation.py").read_text(encoding="utf-8-sig")
    assert "site_state is SiteState.ACTIVE and not site.is_active" in text
    assert 'raise ScopeStateError("site is inactive")' in text
'@
    Set-Content $Test $testText -Encoding UTF8

    Write-Host "[6] Syntax checks"
    docker compose exec -T backend python -m py_compile app/services/isolation.py app/services/planning_runs.py app/services/planning_orchestrator.py app/api/v1/track_b.py tests/test_track_b_planning_site_lifecycle_bridge_v1.py
    if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

    Write-Host "[7] Focused lifecycle bridge tests"
    docker compose exec -T backend python -m pytest -q tests/test_track_b_planning_site_lifecycle_bridge_v1.py
    if($LASTEXITCODE-ne 0){ throw "Lifecycle bridge regression failed." }

    Write-Host "[8] Preserve dispatcher and document regressions"
    foreach($T in @(
        "tests/test_track_b_planning_question_dispatcher_v1.py",
        "tests/test_track_b_planning_question_dispatcher_manifest_v1_2.py",
        "tests/test_planning_document_auto_research.py",
        "tests/test_document_retrieval.py"
    )){
        if(Test-Path "$Root\backend\$T"){
            docker compose exec -T backend python -m pytest -q $T
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $T" }
        }
    }

    Write-Host "[9] Safety verification"
    $iso=Get-Content $Isolation -Raw
    $api=Get-Content $TrackBApi -Raw
    if($iso -notmatch 'site_state: SiteState = SiteState\.ACTIVE'){ throw "Default ACTIVE scope not preserved." }
    if($iso -notmatch 'SiteState\.AVAILABLE, SiteState\.ACTIVE'){ throw "Archived-site rejection contract missing." }
    if($api -notmatch 'site_state=SiteState\.AVAILABLE'){ throw "Track B AVAILABLE opt-in missing." }
    Write-Host "default_active_scope=PRESERVED"
    Write-Host "track_b_available_scope=ENABLED"
    Write-Host "archived_site_rejection=PRESERVED"

    Write-Host "[10] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[11] Backend health"
    docker compose ps backend

    Write-Host "[12] Runtime signature verification"
    docker compose exec -T backend python -c "import inspect; from app.services.isolation import resolve_analysis_scope,SiteState; from app.services.planning_runs import create_planning_run,get_planning_run; from app.services.planning_orchestrator import execute_planning_run; assert inspect.signature(resolve_analysis_scope).parameters['site_state'].default is SiteState.ACTIVE; assert inspect.signature(create_planning_run).parameters['site_state'].default is SiteState.ACTIVE; assert inspect.signature(get_planning_run).parameters['site_state'].default is SiteState.ACTIVE; assert inspect.signature(execute_planning_run).parameters['site_state'].default is SiteState.ACTIVE; print('runtime_lifecycle_contract=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Runtime signature verification failed." }

    Write-Host "============================================================"
    Write-Host "TRACK B PLANNING SITE LIFECYCLE BRIDGE V1 PASS"
    Write-Host "============================================================"
    Write-Host "Normal PlanningRun Site requirement: ACTIVE (PRESERVED)"
    Write-Host "Track B document/policy PlanningRun Site requirement: AVAILABLE"
    Write-Host "Inactive but unarchived Track B Site: ALLOWED FOR THIS ROUTE"
    Write-Host "Archived Site: STILL REJECTED"
    Write-Host "Project ownership isolation: PRESERVED"
    Write-Host "Site/project identity isolation: PRESERVED"
    Write-Host "Project archived rejection: PRESERVED"
    Write-Host "Site DB flags changed: NONE"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend change: NONE"
    Write-Host "Next gate: RETEST LIVE GPP QUESTION"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring full source/test backup."
    Copy-Item "$Backup\isolation.py" $Isolation -Force
    Copy-Item "$Backup\planning_runs.py" $PlanningRuns -Force
    Copy-Item "$Backup\planning_orchestrator.py" $Orchestrator -Force
    Copy-Item "$Backup\track_b_api.py" $TrackBApi -Force
    if(Test-Path "$Backup\test_track_b_planning_site_lifecycle_bridge_v1.py"){
        Copy-Item "$Backup\test_track_b_planning_site_lifecycle_bridge_v1.py" $Test -Force
    } else {
        Remove-Item $Test -Force -ErrorAction SilentlyContinue
    }
    throw
}
