
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$page = ".\frontend\src\pages\TrackBWorkspacePage.tsx"
if (-not (Test-Path $page)) { throw "TrackBWorkspacePage.tsx not found" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = ".\artifacts\trackb_map_frontend_backup_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $page "$backup\TrackBWorkspacePage.tsx"
Write-Host "BACKUP: $backup"

$text = Get-Content $page -Raw
if ($text -notmatch "TRACKB_MISSION_MAP_WIRING_V1") {
    $oldState = '  const [hackathonWorkflow, setHackathonWorkflow] = useState<TrackBWorkflow>();'
    if (-not $text.Contains($oldState)) { throw "State marker not found" }
    $text = $text.Replace(
        $oldState,
        $oldState + "`r`n  const [missionMapView, setMissionMapView] = useState<""urban"" | ""rural"">(""urban"");"
    )

    $startText = '  const runHackathonSimulation = async () => {'
    $endText = '  if (!projectId) return <Navigate to="/projects" replace />;'
    $start = $text.IndexOf($startText)
    $end = $text.IndexOf($endText, $start)
    if ($start -lt 0 -or $end -lt 0) { throw "Mission function markers not found" }

    $replacement = @'
  // TRACKB_MISSION_MAP_WIRING_V1
  const showMissionAnalysis = async (workflow: TrackBWorkflow, view: "urban" | "rural") => {
    if (!token) return;
    const analysis = view === "urban" ? workflow.urban_analysis : workflow.rural_analysis;
    const interpretation = view === "urban" ? workflow.urban_ai : workflow.rural_ai;
    const plannerDecision = view === "urban" ? workflow.urban_decision : workflow.rural_decision;

    setMissionMapView(view);
    setResult(analysis);
    setAiInsight(interpretation ?? undefined);
    setDecision(plannerDecision ?? undefined);
    setSiteId(analysis.site_id);
    setBeforeId(analysis.before_raster_id);
    setAfterId(analysis.after_raster_id);

    if (analysis.change_geojson_url) {
      setGeojson(await trackBApi.fetchGeoJson(analysis.change_geojson_url, token));
    } else {
      setGeojson(undefined);
    }
  };

  const runHackathonSimulation = async () => {
    if (!projectId || !token) return;
    setHackathonBusy(true); setError(undefined);
    try {
      const workflow = await trackBApi.runHackathonWorkflow(projectId, {
        mode,
        absolute_delta_threshold: threshold,
        minimum_usable_coverage_percent: 90,
        planner_question: plannerQuestion.trim() || null,
      }, token);
      setHackathonWorkflow(workflow);
      await showMissionAnalysis(workflow, "urban");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : "Hackathon workflow failed.");
    } finally { setHackathonBusy(false); }
  };

'@
    $text = $text.Substring(0, $start) + $replacement + $text.Substring($end)

    $oldMap = @'
            <div className="map-hud"><span>SPATIAL CHANGE LAYER</span><span className="live-chip">â— deterministic</span></div>
            <TrackBMap geojson={geojson} />
            {!result && <div className="map-empty"><strong>Awaiting temporal run</strong><span>Select T1 + T2 to generate measured change geometry.</span></div>}
'@

    $newMap = @'
            <div className="map-hud">
              <span>SPATIAL CHANGE LAYER</span>
              {hackathonWorkflow && <div className="trackb-mode-tabs">
                <button className={missionMapView === "urban" ? "active" : ""} onClick={() => void showMissionAnalysis(hackathonWorkflow, "urban")}>Urban</button>
                <button className={missionMapView === "rural" ? "active" : ""} onClick={() => void showMissionAnalysis(hackathonWorkflow, "rural")}>Rural</button>
              </div>}
              <span className="live-chip">â— deterministic</span>
            </div>
            <TrackBMap geojson={geojson} />
            {!geojson && <div className="map-empty"><strong>Awaiting spatial change geometry</strong><span>Run temporal intelligence or the full Track B mission to render measured change geometry.</span></div>}
'@

    if (-not $text.Contains($oldMap)) { throw "Map marker not found" }
    $text = $text.Replace($oldMap, $newMap)

    Set-Content -Path $page -Value $text -Encoding UTF8
    Write-Host "PATCHED: $page"
} else {
    Write-Host "Patch already present"
}

Write-Host "[1/3] TypeScript gate..."
docker compose exec frontend npm run typecheck
if ($LASTEXITCODE -ne 0) { throw "TypeScript gate failed" }

Write-Host "[2/3] Restarting frontend..."
docker compose restart frontend
if ($LASTEXITCODE -ne 0) { throw "Frontend restart failed" }

Write-Host "[3/3] Container status..."
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "docker compose ps failed" }

Write-Host ""
Write-Host "MAP PATCH GATE PASS"
Write-Host "Refresh GeoPilot once, then run ONE Full Track B Mission."
Write-Host "Urban displays automatically; Urban/Rural buttons switch map context."
