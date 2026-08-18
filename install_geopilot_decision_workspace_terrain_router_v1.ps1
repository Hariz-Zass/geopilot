$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Page = Join-Path $Root "frontend\src\pages\TrackBWorkspacePage.tsx"
if (!(Test-Path $Page)) {
    throw "TrackBWorkspacePage.tsx not found. Run this installer from geopilot_v7 root."
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root "artifacts\decision_workspace_terrain_router_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Page (Join-Path $Backup "TrackBWorkspacePage.tsx")

Write-Host "============================================================"
Write-Host "GeoPilot Decision Workspace Terrain Router V1"
Write-Host "Terrain question -> Planning Orchestrator -> terrain.site_summary"
Write-Host "Temporal question -> existing Track B decision workspace"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"
Write-Host ""

$text = Get-Content -Raw -Encoding UTF8 $Page

if ($text.Contains("DECISION_WORKSPACE_TERRAIN_ROUTER_V1")) {
    Write-Host "[1] Patch already present. Skipping source modification."
} else {
    Write-Host "[1] Patch Track B Decision Workspace terrain routing"

    $oldImport = 'import { trackBApi, type TrackBAIInterpretation, type TrackBAnalysis, type TrackBDataset, type TrackBPlannerDecision, type TrackBWorkflow, type TrackBReadiness } from "../lib/api/trackB";'
    $newImport = @'
import { trackBApi, type TrackBAIInterpretation, type TrackBAnalysis, type TrackBDataset, type TrackBPlannerDecision, type TrackBWorkflow, type TrackBReadiness } from "../lib/api/trackB";
import { planningRunsApi, type PlanningRunResponse } from "../lib/api/planningRuns";
'@
    if (-not $text.Contains($oldImport)) { throw "Expected Track B import marker not found." }
    $text = $text.Replace($oldImport, $newImport.TrimEnd())

    $stateMarker = '  const [decision, setDecision] = useState<TrackBPlannerDecision>();'
    $stateReplacement = @'
  const [decision, setDecision] = useState<TrackBPlannerDecision>();
  // DECISION_WORKSPACE_TERRAIN_ROUTER_V1
  const [terrainPlanningRun, setTerrainPlanningRun] =
    useState<PlanningRunResponse>();
'@
    if (-not $text.Contains($stateMarker)) { throw "Expected decision state marker not found." }
    $text = $text.Replace($stateMarker, $stateReplacement.TrimEnd())

    $functionMarker = @'
  async function runPlannerDecision() {
    if (!projectId || !token || !result) return;
    setAiBusy(true); setError(undefined);
    try {
      setDecision(await trackBApi.decisionWorkspace(projectId, result.analysis_id, plannerQuestion, token));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : caught instanceof Error ? caught.message : "Planner decision workspace failed.");
    } finally { setAiBusy(false); }
  }
'@

    $functionReplacement = @'
  function isTerrainMeasurementQuestion(value: string) {
    const q = value.toLocaleLowerCase().replace(/\s+/g, " ").trim();

    const terrainTerms = [
      "slope", "gradient", "terrain", "topography", "topographic",
      "elevation", "altitude", "contour", "dem", "kecerunan",
      "cerun", "elevasi", "aras tanah", "kontur", "topografi",
    ];
    const measurementTerms = [
      "berapa", "what is", "highest", "lowest", "maximum", "minimum",
      "max ", "min ", "average", "mean", "purata", "tertinggi",
      "terendah", "nilai", "calculate", "measure", "ukur", "kira",
      "site", "tapak", "kawasan",
    ];
    const policyTerms = [
      "policy", "standard", "guideline", "requirement", "allowed",
      "permitted", "statutory", "gpp", "rfn", "rsn", "rkk",
      "rancangan tempatan", "garis panduan", "piawaian", "syarat",
      "dibenarkan", "had",
    ];

    const contains = (terms: string[]) =>
      terms.some((term) => q.includes(term));

    return contains(terrainTerms) &&
      contains(measurementTerms) &&
      !contains(policyTerms);
  }

  async function runPlannerDecision() {
    if (!projectId || !token || !result || !siteId) return;

    setAiBusy(true);
    setError(undefined);

    try {
      if (isTerrainMeasurementQuestion(plannerQuestion)) {
        // Terrain measurements must use the normal evidence-bounded
        // Planning Orchestrator, which routes to terrain.site_summary.
        // This preserves manual DEM precedence and automatic CDSE fallback.
        const created = await planningRunsApi.create(
          projectId,
          siteId,
          {
            question: plannerQuestion.trim(),
            development_intent: null,
          },
          token,
        );
        const executed = await planningRunsApi.execute(
          projectId,
          siteId,
          created.id,
          token,
        );

        setTerrainPlanningRun(executed);
        setDecision(undefined);
        return;
      }

      setTerrainPlanningRun(undefined);
      setDecision(
        await trackBApi.decisionWorkspace(
          projectId,
          result.analysis_id,
          plannerQuestion,
          token,
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "Planner decision workspace failed.",
      );
    } finally {
      setAiBusy(false);
    }
  }
'@
    if (-not $text.Contains($functionMarker)) { throw "Expected runPlannerDecision function block not found." }
    $text = $text.Replace($functionMarker, $functionReplacement)

    $renderMarker = @'
            {!decision ? <div className="decision-empty"><strong>Decision brief not generated yet</strong><span>GeoPilot will convert the deterministic temporal result into Issue → Evidence → Priority → Planning implication → Action, without treating spectral change as statutory proof.</span></div> : <div className="decision-grid">
'@

    $renderReplacement = @'
            {terrainPlanningRun ? (
              <div className="decision-grid">
                <article className="decision-priority priority-monitor">
                  <small>DETERMINISTIC TERRAIN EVIDENCE</small>
                  <strong>{terrainPlanningRun.status.toUpperCase()}</strong>
                  <span>terrain.site_summary</span>
                  <code>
                    {String(
                      terrainPlanningRun.provider_metadata?.provider ??
                        "evidence-bounded",
                    )} · {String(
                      terrainPlanningRun.provider_metadata?.model ??
                        "deterministic",
                    )}
                  </code>
                </article>

                <article className="decision-core">
                  <small>GEOPILOT TERRAIN ANSWER</small>
                  <h3>Terrain measurement result</h3>
                  <p>
                    {terrainPlanningRun.synthesis ??
                      "AI synthesis unavailable. Deterministic terrain evidence remains available."}
                  </p>
                </article>

                <article className="decision-evidence">
                  <small>EVIDENCE SUMMARY</small>
                  <p>
                    Terrain values are sourced from the validated
                    project/site DEM through terrain.site_summary.
                  </p>
                  <div className="ai-evidence-tags">
                    <code>TERRAIN_SITE_SUMMARY</code>
                    <code>DEM_EVIDENCE</code>
                  </div>
                  <details>
                    <summary>
                      Inspect deterministic evidence
                    </summary>
                    <pre>
                      {JSON.stringify(
                        terrainPlanningRun.evidence,
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </article>

                <article className="decision-limit">
                  <small>LIMITATIONS / REVIEW BOUNDARY</small>
                  {terrainPlanningRun.limitations.length ? (
                    terrainPlanningRun.limitations.map((item, i) => (
                      <p key={`${i}-${String(item).slice(0, 32)}`}>
                        • {String(item)}
                      </p>
                    ))
                  ) : (
                    <p>
                      • Terrain values are deterministic measurements
                      from the selected Site DEM.
                    </p>
                  )}
                  <p>
                    • Professional planning interpretation remains
                    separate from the measured terrain values.
                  </p>
                </article>
              </div>
            ) : !decision ? <div className="decision-empty"><strong>Decision brief not generated yet</strong><span>GeoPilot will convert the deterministic temporal result into Issue → Evidence → Priority → Planning implication → Action, without treating spectral change as statutory proof.</span></div> : <div className="decision-grid">
'@
    if (-not $text.Contains($renderMarker)) { throw "Expected decision render marker not found." }
    $text = $text.Replace($renderMarker, $renderReplacement)

    Set-Content -Path $Page -Value $text -Encoding UTF8
    Write-Host "PATCHED: frontend\src\pages\TrackBWorkspacePage.tsx"
}

Write-Host ""
Write-Host "[2] Frontend production build"
docker compose exec -T frontend npm run build
if ($LASTEXITCODE -ne 0) {
    throw "Frontend production build failed."
}

Write-Host ""
Write-Host "[3] Backend routing + terrain regression gate"
docker compose exec -T backend python -m pytest -q tests/test_data_requirement_router.py tests/test_terrain_analysis.py tests/test_terrain_acquisition.py
if ($LASTEXITCODE -ne 0) {
    throw "Backend terrain/router regression tests failed."
}

Write-Host ""
Write-Host "[4] Verify exact target question routing"
docker compose exec -T backend python -c "from app.services.data_requirement_router import route_question; q='berapa slope paling tinggi di kawasan tersebut?'; r=route_question(q); print('QUESTION:',q); print('STATE:',r.state); print('CAPABILITY:',r.capability); print('TOOLS:',r.tools); assert r.capability=='terrain_measurement' and r.tools==('terrain.site_summary',)"
if ($LASTEXITCODE -ne 0) {
    throw "Exact terrain question routing verification failed."
}

Write-Host ""
Write-Host "[5] Verify frontend terrain router markers"
$verify = Get-Content -Raw -Encoding UTF8 $Page
$markers = @(
    "DECISION_WORKSPACE_TERRAIN_ROUTER_V1",
    "planningRunsApi.create",
    "planningRunsApi.execute",
    "TERRAIN_SITE_SUMMARY",
    "isTerrainMeasurementQuestion"
)
foreach ($marker in $markers) {
    if (-not $verify.Contains($marker)) {
        throw "Missing frontend terrain router marker: $marker"
    }
}
Write-Host "Decision Workspace terrain routing markers: PASS"

Write-Host ""
Write-Host "[6] Service health"
docker compose ps
if ($LASTEXITCODE -ne 0) {
    throw "Docker service health check failed."
}

Write-Host ""
Write-Host "============================================================"
Write-Host "DECISION WORKSPACE TERRAIN ROUTER V1 PASS"
Write-Host "============================================================"
Write-Host "Terrain measurement questions: Planning Orchestrator"
Write-Host "Terrain tool: terrain.site_summary"
Write-Host "Manual DEM precedence: PRESERVED"
Write-Host "Automatic CDSE fallback: PRESERVED"
Write-Host "Temporal Track B questions: EXISTING FLOW PRESERVED"
Write-Host "Track B closed-evidence temporal engine: UNCHANGED"
Write-Host "DB schema change: NONE"
Write-Host "Migration: NONE"
Write-Host "============================================================"
