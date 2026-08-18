$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$AI = Join-Path $Root "backend\app\services\track_b_ai.py"
$API = Join-Path $Root "backend\app\api\v1\track_b.py"
if (!(Test-Path $AI) -or !(Test-Path $API)) {
  throw "Required Track B backend files are missing."
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root "artifacts\trackb_server_terrain_router_v2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $AI (Join-Path $Backup "track_b_ai.py")
Copy-Item $API (Join-Path $Backup "track_b.py")

Write-Host "============================================================"
Write-Host "GeoPilot Track B Server-side Terrain Router V2"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"

$patch = @'
from pathlib import Path

ai = Path("/app/app/services/track_b_ai.py")
api = Path("/app/app/api/v1/track_b.py")

s = ai.read_text(encoding="utf-8-sig")

if "TRACKB_TERRAIN_DECISION_ROUTER_V2" not in s:
    addition = """

# TRACKB_TERRAIN_DECISION_ROUTER_V2
def _terrain_numeric_allowlist(facts: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for value in facts.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            allowed.add(str(value))
            for places in range(0, 9):
                allowed.add(f"{float(value):.{places}f}")
    return allowed


def _validate_terrain_decision_numbers(payload: dict[str, Any], facts: dict[str, Any]) -> None:
    allowed = _terrain_numeric_allowlist(facts)
    narrative = " ".join([
        str(payload.get("decision_title", "")),
        str(payload.get("issue", "")),
        str(payload.get("planning_implication", "")),
        str(payload.get("evidence_summary", "")),
        *[str(x) for x in payload.get("limitations", [])],
        *[
            str(item.get(k, ""))
            for item in payload.get("recommended_actions", [])
            for k in ("action", "rationale", "verification_needed")
        ],
    ])
    narrative = _remove_leading_list_markers(narrative)
    for token in re.findall(r"(?<![A-Za-z])\\d+(?:\\.\\d+)?", narrative):
        if token not in allowed:
            raise TrackBAIError(f"Terrain decision introduced an ungrounded numeric claim: {token}")


def build_track_b_terrain_planner_decision(
    *,
    session,
    owner,
    project_id: uuid.UUID,
    analysis_id: uuid.UUID,
    planner_question: str,
) -> dict[str, Any]:
    from app.services.terrain_analysis import calculate_site_terrain_summary

    path, analysis = _manifest(project_id, analysis_id)
    raw_site_id = analysis.get("site_id")
    if not raw_site_id:
        raise TrackBAIError("Terrain question cannot be executed because the Track B analysis has no Site.")

    try:
        site_id = uuid.UUID(str(raw_site_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise TrackBAIError("Track B analysis contains an invalid Site identifier.") from exc

    summary = calculate_site_terrain_summary(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
    )

    facts = {
        "valid_pixel_count": summary.valid_pixel_count,
        "elevation_min_m": summary.elevation_min_m,
        "elevation_max_m": summary.elevation_max_m,
        "elevation_mean_m": summary.elevation_mean_m,
        "slope_min_degrees": summary.slope_min_degrees,
        "slope_max_degrees": summary.slope_max_degrees,
        "slope_mean_degrees": summary.slope_mean_degrees,
        "max_slope_longitude": summary.max_slope_longitude,
        "max_slope_latitude": summary.max_slope_latitude,
        "crs": summary.crs,
        "raster_checksum_sha256": summary.raster_checksum_sha256,
        "source_uri": summary.source_uri,
    }

    instructions = (
        "You are GeoPilot AI Decision Workspace. Answer the planner's TERRAIN MEASUREMENT "
        "question using ONLY the supplied deterministic terrain facts from terrain.site_summary. "
        "Do not use NDVI, temporal change, basemap appearance, or general knowledge to invent "
        "terrain measurements. If the question asks for highest or maximum slope, answer from "
        "slope_max_degrees. If it asks for maximum elevation, answer from elevation_max_m. "
        "Clearly state the unit. Numeric claims must be copied from supplied terrain facts or "
        "normally rounded from those same facts. Return JSON only with exactly these keys: "
        "confidence, priority, decision_title, issue, planning_implication, evidence_summary, "
        "recommended_actions, evidence_refs, limitations. confidence must be high|moderate|limited. "
        "priority must be high|elevated|monitor|evidence_limited and is non-statutory planner "
        "triage only. recommended_actions must be an array of objects with exactly action, "
        "rationale, evidence_refs, verification_needed. evidence_refs must only contain "
        "TERRAIN_SITE_SUMMARY. limitations must be an array of strings. Keep the direct answer "
        "prominent and concise."
    )

    allowed = sorted(_terrain_numeric_allowlist(facts), key=lambda x: (len(x), x))
    input_text = (
        "PLANNER QUESTION:\\n" + planner_question.strip()
        + "\\n\\nDETERMINISTIC TERRAIN FACTS:\\n"
        + json.dumps(facts, ensure_ascii=False, indent=2, default=str)
        + "\\n\\nALLOWED NUMERIC TOKENS:\\n"
        + ", ".join(allowed)
    )

    try:
        result, failures = generate_with_failover(
            instructions=instructions,
            input_text=input_text,
        )
    except ProviderResilienceError as exc:
        raise TrackBAIError("No configured AI provider is currently available for terrain synthesis.") from exc

    payload = _parse_json(result.text)
    _canonicalize_list_fields(
        payload,
        string_fields=("evidence_refs", "limitations"),
        object_fields=("recommended_actions",),
    )

    required = {
        "confidence", "priority", "decision_title", "issue",
        "planning_implication", "evidence_summary",
        "recommended_actions", "evidence_refs", "limitations",
    }
    if set(payload) != required:
        raise TrackBAIError("AI provider returned a response outside the terrain decision contract.")

    if payload.get("confidence") not in {"high", "moderate", "limited"}:
        raise TrackBAIError("AI provider returned an invalid terrain confidence.")

    if payload.get("priority") not in {"high", "elevated", "monitor", "evidence_limited"}:
        raise TrackBAIError("AI provider returned an invalid terrain triage priority.")

    refs = payload.get("evidence_refs", [])
    if not isinstance(refs, list) or any(ref != "TERRAIN_SITE_SUMMARY" for ref in refs):
        raise TrackBAIError("Terrain synthesis referenced evidence outside terrain.site_summary.")

    actions = payload.get("recommended_actions", [])
    if not isinstance(actions, list):
        raise TrackBAIError("AI provider returned invalid terrain actions.")

    for action in actions:
        if not isinstance(action, dict) or set(action) != {
            "action", "rationale", "evidence_refs", "verification_needed"
        }:
            raise TrackBAIError("AI provider returned an invalid terrain action object.")
        action_refs = action.get("evidence_refs", [])
        if not isinstance(action_refs, list) or any(
            ref != "TERRAIN_SITE_SUMMARY" for ref in action_refs
        ):
            raise TrackBAIError("Terrain action referenced evidence outside terrain.site_summary.")

    _validate_terrain_decision_numbers(payload, facts)

    response = {
        "analysis_id": analysis_id,
        "provider": result.provider,
        "model": result.model,
        **payload,
        "planner_question": planner_question.strip(),
        "evidence_policy": "project_site_terrain_evidence",
        "professional_review_required": True,
    }

    terrain_path = path.parent / "planner_decision_terrain.json"
    terrain_path.write_text(
        json.dumps(response, default=str, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return response
"""
    s = s.rstrip() + addition + "\n"
    ai.write_text(s, encoding="utf-8")
    print("PATCHED:", ai)
else:
    print("SKIP: Track B terrain AI router V2 already present.")

a = api.read_text(encoding="utf-8-sig")

if "from app.services.data_requirement_router import route_question" not in a:
    marker = "from app.models.user import User\n"
    if marker not in a:
        raise SystemExit("BLOCKED: track_b API User import marker missing.")
    a = a.replace(
        marker,
        marker + "from app.services.data_requirement_router import route_question\n",
        1,
    )

if "build_track_b_terrain_planner_decision" not in a:
    target = "build_track_b_planner_decision,"
    if target in a:
        a = a.replace(
            target,
            target + "\n    build_track_b_terrain_planner_decision,",
            1,
        )
    else:
        target2 = "build_track_b_planner_decision"
        if target2 not in a:
            raise SystemExit("BLOCKED: build_track_b_planner_decision import not found.")
        a = a.replace(
            target2,
            target2 + ", build_track_b_terrain_planner_decision",
            1,
        )

old = """        return build_track_b_planner_decision(
            project_id=project_id,
            analysis_id=analysis_id,
            planner_question=payload.planner_question,
        )
"""
new = """        question = (payload.planner_question or "").strip()
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
"""

if 'route.capability == "terrain_measurement"' not in a:
    if old not in a:
        raise SystemExit("BLOCKED: planner_decision_workspace return block not found.")
    a = a.replace(old, new, 1)
    print("PATCHED:", api)
else:
    print("SKIP: server-side endpoint terrain routing already present.")

api.write_text(a, encoding="utf-8")
'@

Write-Host "[1] Apply server-side terrain router"
$patch | docker compose exec -T backend python -
if ($LASTEXITCODE -ne 0) { throw "Backend patch failed." }

Write-Host ""
Write-Host "[2] Python syntax checks"
docker compose exec -T backend python -m py_compile app/services/track_b_ai.py app/api/v1/track_b.py
if ($LASTEXITCODE -ne 0) { throw "Backend syntax check failed." }

Write-Host ""
Write-Host "[3] Terrain + router regression tests"
docker compose exec -T backend python -m pytest -q tests/test_data_requirement_router.py tests/test_terrain_analysis.py tests/test_terrain_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Terrain/router regression tests failed." }

Write-Host ""
Write-Host "[4] Exact question route verification"
docker compose exec -T backend python -c "from app.services.data_requirement_router import route_question; q='berapa slope paling tinggi di kawasan tersebut?'; r=route_question(q); print('capability=',r.capability); print('tools=',r.tools); assert r.capability=='terrain_measurement' and r.tools==('terrain.site_summary',)"
if ($LASTEXITCODE -ne 0) { throw "Exact question route verification failed." }

Write-Host ""
Write-Host "[5] Verify live endpoint terrain branch"
docker compose exec -T backend python -c "import inspect; from app.api.v1.track_b import planner_decision_workspace; s=inspect.getsource(planner_decision_workspace); print('server_terrain_branch=', 'terrain_measurement' in s and 'build_track_b_terrain_planner_decision' in s); assert 'terrain_measurement' in s and 'build_track_b_terrain_planner_decision' in s"
if ($LASTEXITCODE -ne 0) { throw "Live endpoint terrain branch verification failed." }

Write-Host ""
Write-Host "[6] Restart backend"
docker compose restart backend
if ($LASTEXITCODE -ne 0) { throw "Backend restart failed." }
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "[7] Service health"
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "Service health check failed." }

Write-Host ""
Write-Host "============================================================"
Write-Host "TRACK B SERVER-SIDE TERRAIN ROUTER V2 PASS"
Write-Host "============================================================"
Write-Host "Existing decision-workspace endpoint: TERRAIN AWARE"
Write-Host "Exact slope question: terrain_measurement"
Write-Host "Terrain source: terrain.site_summary"
Write-Host "Manual DEM precedence: PRESERVED"
Write-Host "Automatic CDSE fallback: PRESERVED"
Write-Host "AI terrain synthesis: ENABLED"
Write-Host "Temporal Track B flow: PRESERVED"
Write-Host "Frontend routing dependency: NOT REQUIRED"
Write-Host "DB schema change: NONE"
Write-Host "Migration: NONE"
Write-Host "============================================================"
