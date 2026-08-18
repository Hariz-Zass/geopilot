$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Api="$Root\backend\app\api\v1\track_b.py"
$Frontend="$Root\frontend\src\pages\TrackBWorkspacePage.tsx"
$Test="$Root\backend\tests\test_track_b_planning_question_dispatcher_v1.py"
foreach($P in @($Api,$Frontend)){ if(!(Test-Path $P)){ throw "Missing required file: $P" } }
Write-Host "============================================================"
Write-Host "GeoPilot Track B Planning Question Dispatcher V1"
Write-Host "Document/policy questions -> existing Planning Orchestrator"
Write-Host "Terrain questions -> existing terrain path"
Write-Host "Temporal/raster questions -> existing Track B AI"
Write-Host "NO DB SCHEMA CHANGE / NO MIGRATION"
Write-Host "============================================================"
$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\track_b_planning_question_dispatcher_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Api "$Backup\track_b_api.py"
Copy-Item $Frontend "$Backup\TrackBWorkspacePage.tsx"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_track_b_planning_question_dispatcher_v1.py" }
Write-Host "BACKUP: $Backup"
try {
  Write-Host "[0] Preflight call-path gate"
  $apiText=Get-Content $Api -Raw
  if($apiText -notmatch 'route_question\(question\)'){ throw "Expected route_question call not found." }
  if($apiText -notmatch 'build_track_b_terrain_planner_decision'){ throw "Expected terrain decision path not found." }
  if($apiText -notmatch 'build_track_b_planner_decision'){ throw "Expected temporal Track B decision path not found." }
  if($apiText -match 'execute_planning_run'){ throw "Planning orchestrator already wired into Track B API; stop to avoid duplicate patch." }
  Write-Host "preflight_state=CONFIRMED"

  Write-Host "[1] Patch Track B API dispatcher"
  $patch=@'
from pathlib import Path
path = Path("/app/app/api/v1/track_b.py")
text = path.read_text(encoding="utf-8-sig")
if "from app.schemas.planning_run import PlanningRunCreate" not in text:
    anchor = "from app.services.data_requirement_router import route_question\n"
    if anchor not in text:
        raise SystemExit("IMPORT_ANCHOR_NOT_FOUND")
    text = text.replace(anchor, anchor + "from app.schemas.planning_run import PlanningRunCreate\nfrom app.services.planning_runs import create_planning_run\nfrom app.services.planning_orchestrator import execute_planning_run\n", 1)
marker = "# TRACKB_PLANNING_QUESTION_DISPATCHER_V1"
if marker not in text:
    router_anchor = '@router.post("/analyses/{analysis_id}/decision-workspace", response_model=TrackBPlannerDecisionResponse)\n'
    if router_anchor not in text:
        raise SystemExit("DECISION_ROUTE_ANCHOR_NOT_FOUND")
    helper = '''
# TRACKB_PLANNING_QUESTION_DISPATCHER_V1
def _planning_run_to_track_b_decision(*, analysis_id: uuid.UUID, question: str, run):
    provider_metadata = run.provider_metadata or {}
    evidence = run.evidence or []
    limitations = list(run.limitations or [])
    refs = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") or {}
        ref = payload.get("citation_label") or payload.get("document_title") or item.get("tool_name")
        if ref:
            refs.append(str(ref))
    refs = list(dict.fromkeys(refs))
    completed = run.status == "completed" and bool(run.synthesis)
    synthesis = (run.synthesis or "").strip()
    if not synthesis:
        synthesis = "GeoPilot could not produce a grounded planning answer from the currently available validated evidence."
    return {
        "analysis_id": analysis_id,
        "provider": str(provider_metadata.get("provider") or "planning_orchestrator"),
        "model": str(provider_metadata.get("model") or "evidence-router"),
        "confidence": "moderate" if completed else "limited",
        "priority": "monitor" if completed else "evidence_limited",
        "decision_title": "Grounded planning evidence response",
        "issue": question,
        "planning_implication": synthesis,
        "evidence_summary": synthesis,
        "recommended_actions": [],
        "evidence_refs": refs,
        "limitations": limitations,
        "planner_question": question,
        "evidence_architecture": "provenance_controlled",
        "evidence_policy": "provenance_controlled",
        "professional_review_required": True,
    }

def _run_track_b_planning_question(session: Session, *, owner: User, project_id: uuid.UUID, site_id: uuid.UUID, analysis_id: uuid.UUID, question: str):
    run = create_planning_run(session, owner=owner, project_id=project_id, site_id=site_id, request=PlanningRunCreate(question=question, development_intent=None))
    run = execute_planning_run(session, owner=owner, project_id=project_id, site_id=site_id, run_id=run.id)
    return _planning_run_to_track_b_decision(analysis_id=analysis_id, question=question, run=run)

'''
    text = text.replace(router_anchor, helper + router_anchor, 1)
old = '''        question = (payload.planner_question or "").strip()
        route = route_question(question) if question else None
        if route is not None and route.capability == "terrain_measurement":
            return build_track_b_terrain_planner_decision(
                session=session,
                owner=current_user,
                project_id=project_id,
                analysis_id=analysis_id,
                planner_question=question,
            )
        return build_track_b_planner_decision(
            project_id=project_id,
            analysis_id=analysis_id,
            planner_question=payload.planner_question,
        )
'''
new = '''        question = (payload.planner_question or "").strip()
        route = route_question(question) if question else None
        if route is not None and route.capability == "terrain_measurement":
            return build_track_b_terrain_planner_decision(
                session=session,
                owner=current_user,
                project_id=project_id,
                analysis_id=analysis_id,
                planner_question=question,
            )
        if route is not None and "documents.search" in route.tools:
            analysis = get_track_b_analysis_manifest(project_id=project_id, analysis_id=analysis_id)
            site_id = analysis.get("site_id")
            if not site_id:
                raise TrackBAIError("Planning-document research requires the Track B analysis to be linked to a Site.")
            return _run_track_b_planning_question(
                session,
                owner=current_user,
                project_id=project_id,
                site_id=uuid.UUID(str(site_id)),
                analysis_id=analysis_id,
                question=question,
            )
        return build_track_b_planner_decision(
            project_id=project_id,
            analysis_id=analysis_id,
            planner_question=payload.planner_question,
        )
'''
if old not in text:
    raise SystemExit("DISPATCHER_BLOCK_NOT_FOUND")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("PATCHED:", path)
'@
  $Temp="$Root\backend\_patch_track_b_planning_question_dispatcher_v1.py"
  Set-Content $Temp $patch -Encoding UTF8
  try {
    docker compose exec -T backend python /app/_patch_track_b_planning_question_dispatcher_v1.py
    if($LASTEXITCODE-ne 0){ throw "Track B API dispatcher patch failed." }
  } finally { Remove-Item $Temp -Force -ErrorAction SilentlyContinue }

  Write-Host "[2] Repair stale frontend wording only"
  $front=Get-Content $Frontend -Raw
  $front=$front.Replace('Every claim stays inside organizer evidence.','Every claim stays grounded in validated project, official-document, terrain, GIS, or temporal evidence.')
  $front=$front.Replace('auditable organizer sources','auditable evidence sources')
  Set-Content $Frontend $front -Encoding UTF8

  Write-Host "[3] Install focused dispatcher regression tests"
  $testText=@'
from types import SimpleNamespace
import uuid

def test_planning_run_adapter_preserves_track_b_contract():
    from app.api.v1.track_b import _planning_run_to_track_b_decision
    analysis_id = uuid.uuid4()
    run = SimpleNamespace(status="completed", synthesis="The retrieved GPP states the grounded planning requirement.", provider_metadata={"provider": "openai", "model": "test-model"}, limitations=[], evidence=[{"tool_name": "documents.search", "payload": {"citation_label": "GPP Test — p. 12", "document_title": "GPP Test"}}])
    result = _planning_run_to_track_b_decision(analysis_id=analysis_id, question="What does the GPP state?", run=run)
    assert result["analysis_id"] == analysis_id
    assert result["provider"] == "openai"
    assert result["model"] == "test-model"
    assert result["confidence"] == "moderate"
    assert result["priority"] == "monitor"
    assert result["planning_implication"] == run.synthesis
    assert result["evidence_refs"] == ["GPP Test — p. 12"]
    assert result["evidence_architecture"] == "provenance_controlled"

def test_planning_run_adapter_degrades_safely_without_synthesis():
    from app.api.v1.track_b import _planning_run_to_track_b_decision
    result = _planning_run_to_track_b_decision(analysis_id=uuid.uuid4(), question="What policy applies?", run=SimpleNamespace(status="degraded", synthesis=None, provider_metadata={}, limitations=["No matching official document evidence was found."], evidence=[]))
    assert result["confidence"] == "limited"
    assert result["priority"] == "evidence_limited"
    assert result["limitations"]

def test_track_b_api_dispatcher_reuses_planning_orchestrator():
    from pathlib import Path
    text = Path("app/api/v1/track_b.py").read_text(encoding="utf-8-sig")
    assert "TRACKB_PLANNING_QUESTION_DISPATCHER_V1" in text
    assert '"documents.search" in route.tools' in text
    assert "create_planning_run(" in text
    assert "execute_planning_run(" in text
    assert "build_track_b_terrain_planner_decision(" in text
    assert "build_track_b_planner_decision(" in text
'@
  Set-Content $Test $testText -Encoding UTF8

  Write-Host "[4] Syntax checks"
  docker compose exec -T backend python -m py_compile app/api/v1/track_b.py tests/test_track_b_planning_question_dispatcher_v1.py
  if($LASTEXITCODE-ne 0){ throw "Backend syntax check failed." }

  Write-Host "[5] Focused dispatcher tests"
  docker compose exec -T backend python -m pytest -q tests/test_track_b_planning_question_dispatcher_v1.py
  if($LASTEXITCODE-ne 0){ throw "Dispatcher regression failed." }

  Write-Host "[6] Preserve Auto Research + retrieval regressions"
  foreach($T in @("tests/test_planning_document_auto_research.py","tests/test_planning_document_acquisition.py","tests/test_document_retrieval.py")){
    if(Test-Path "$Root\backend\$T"){
      docker compose exec -T backend python -m pytest -q $T
      if($LASTEXITCODE-ne 0){ throw "Regression failed: $T" }
    }
  }

  Write-Host "[7] Preserve Track B regressions"
  foreach($T in @("tests/test_track_b_hackathon.py","tests/test_track_b_acceptance.py")){
    if(Test-Path "$Root\backend\$T"){
      docker compose exec -T backend python -m pytest -q $T
      if($LASTEXITCODE-ne 0){ throw "Regression failed: $T" }
    }
  }

  Write-Host "[8] Frontend production build"
  docker compose exec -T frontend npm run build
  if($LASTEXITCODE-ne 0){ throw "Frontend build failed." }

  Write-Host "[9] Recreate backend + restart frontend"
  docker compose up -d --no-deps --force-recreate backend
  if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }
  docker compose restart frontend
  if($LASTEXITCODE-ne 0){ throw "Frontend restart failed." }
  Start-Sleep -Seconds 5
  docker compose ps

  Write-Host "============================================================"
  Write-Host "TRACK B PLANNING QUESTION DISPATCHER V1 PASS"
  Write-Host "============================================================"
  Write-Host "Terrain measurement questions: EXISTING TERRAIN PATH"
  Write-Host "Planning document/policy questions: PLANNING ORCHESTRATOR"
  Write-Host "Auto Research RT/RSN/RKK/GPP: REUSED"
  Write-Host "documents.search retrieval + citations: REUSED"
  Write-Host "Temporal/raster questions: EXISTING TRACK B AI"
  Write-Host "Track B response contract: PRESERVED"
  Write-Host "OpenAI/Ollama planning providers: UNCHANGED"
  Write-Host "Anti-hallucination / evidence validation: PRESERVED"
  Write-Host "DB schema change: NONE"
  Write-Host "Migration: NONE"
  Write-Host "Runtime PlanningRun rows: CREATED ONLY WHEN USER ASKS A DOCUMENT/POLICY QUESTION"
  Write-Host "Next gate: LIVE GPP DOCUMENT-EVIDENCE E2E"
  Write-Host "============================================================"
}
catch {
  Write-Host "INSTALL FAILED - restoring API/frontend/test backup."
  Copy-Item "$Backup\track_b_api.py" $Api -Force
  Copy-Item "$Backup\TrackBWorkspacePage.tsx" $Frontend -Force
  if(Test-Path "$Backup\test_track_b_planning_question_dispatcher_v1.py"){
    Copy-Item "$Backup\test_track_b_planning_question_dispatcher_v1.py" $Test -Force
  } else { Remove-Item $Test -Force -ErrorAction SilentlyContinue }
  throw
}
