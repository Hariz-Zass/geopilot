
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$page = ".\frontend\src\pages\TrackBWorkspacePage.tsx"
if (-not (Test-Path $page)) { throw "TrackBWorkspacePage.tsx not found" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = ".\artifacts\trackb_map_frontend_backup_v2_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $page "$backup\TrackBWorkspacePage.tsx"
Write-Host "BACKUP: $backup"

$text = Get-Content $page -Raw

if ($text -notmatch "TRACKB_MISSION_MAP_WIRING_V2") {

    # 1) Add mission map view state if missing.
    if ($text -notmatch 'missionMapView') {
        $statePattern = [regex]::Escape('  const [hackathonWorkflow, setHackathonWorkflow] = useState<TrackBWorkflow>();')
        if (-not [regex]::IsMatch($text, $statePattern)) {
            throw "State marker not found"
        }
        $text = [regex]::Replace(
            $text,
            $statePattern,
            '  const [hackathonWorkflow, setHackathonWorkflow] = useState<TrackBWorkflow>();' + "`r`n" +
            '  const [missionMapView, setMissionMapView] = useState<"urban" | "rural">("urban");',
            1
        )
    }

    # 2) Replace runHackathonSimulation with mission -> map wiring.
    $startText = '  const runHackathonSimulation = async () => {'
    $endText = '  if (!projectId) return <Navigate to="/projects" replace />;'
    $start = $text.IndexOf($startText)
    $end = $text.IndexOf($endText, $start)

    if ($start -lt 0 -or $end -lt 0) {
        throw "Mission function markers not found"
    }

    $replacement = @'
  // TRACKB_MISSION_MAP_WIRING_V2
  const showMissionAnalysis = async (
    workflow: TrackBWorkflow,
    view: "urban" | "rural",
  ) => {
    if (!token) return;

    const analysis = view === "urban"
      ? workflow.urban_analysis
      : workflow.rural_analysis;
    const interpretation = view === "urban"
      ? workflow.urban_ai
      : workflow.rural_ai;
    const plannerDecision = view === "urban"
      ? workflow.urban_decision
      : workflow.rural_decision;

    setMissionMapView(view);
    setResult(analysis);
    setAiInsight(interpretation ?? undefined);
    setDecision(plannerDecision ?? undefined);
    setSiteId(analysis.site_id);
    setBeforeId(analysis.before_raster_id);
    setAfterId(analysis.after_raster_id);

    if (analysis.change_geojson_url) {
      const nextGeoJson = await trackBApi.fetchGeoJson(
        analysis.change_geojson_url,
        token,
      );
      setGeojson(nextGeoJson);
    } else {
      setGeojson(undefined);
    }
  };

  const runHackathonSimulation = async () => {
    if (!projectId || !token) return;

    setHackathonBusy(true);
    setError(undefined);

    try {
      const workflow = await trackBApi.runHackathonWorkflow(
        projectId,
        {
          mode,
          absolute_delta_threshold: threshold,
          minimum_usable_coverage_percent: 90,
          planner_question: plannerQuestion.trim() || null,
        },
        token,
      );

      setHackathonWorkflow(workflow);

      // Default judge/demo map to the Urban mission result.
      await showMissionAnalysis(workflow, "urban");
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : cause instanceof Error
            ? cause.message
            : "Hackathon workflow failed.",
      );
    } finally {
      setHackathonBusy(false);
    }
  };

'@

    $text = $text.Substring(0, $start) + $replacement + $text.Substring($end)

    # 3) Replace map HUD and empty overlay using structural regex, independent of encoding.
    $mapPattern = '(?s)<div className="map-hud">.*?</div>\s*<TrackBMap geojson=\{geojson\} />\s*\{!result && <div className="map-empty">.*?</div>\}'
    $mapReplacement = @'
<div className="map-hud">
              <span>SPATIAL CHANGE LAYER</span>
              {hackathonWorkflow && <div className="trackb-mode-tabs">
                <button
                  className={missionMapView === "urban" ? "active" : ""}
                  onClick={() => void showMissionAnalysis(hackathonWorkflow, "urban")}
                >
                  Urban
                </button>
                <button
                  className={missionMapView === "rural" ? "active" : ""}
                  onClick={() => void showMissionAnalysis(hackathonWorkflow, "rural")}
                >
                  Rural
                </button>
              </div>}
              <span className="live-chip">deterministic</span>
            </div>
            <TrackBMap geojson={geojson} />
            {!geojson && <div className="map-empty"><strong>Awaiting spatial change geometry</strong><span>Run temporal intelligence or the full Track B mission to render measured change geometry.</span></div>}
'@

    if (-not [regex]::IsMatch($text, $mapPattern)) {
        throw "Map structure not found"
    }

    $text = [regex]::Replace($text, $mapPattern, $mapReplacement, 1)

    Set-Content -Path $page -Value $text -Encoding UTF8
    Write-Host "PATCHED: $page"
} else {
    Write-Host "V2 patch already present"
}

Write-Host ""
Write-Host "[1/4] Inspecting patched markers..."
Select-String -Path $page -Pattern "TRACKB_MISSION_MAP_WIRING_V2|showMissionAnalysis|missionMapView|Awaiting spatial change geometry"

Write-Host ""
Write-Host "[2/4] Running frontend TypeScript gate..."
docker compose exec frontend npm run typecheck
if ($LASTEXITCODE -ne 0) { throw "TypeScript gate failed" }

Write-Host ""
Write-Host "[3/4] Restarting frontend only..."
docker compose restart frontend
if ($LASTEXITCODE -ne 0) { throw "Frontend restart failed" }

Write-Host ""
Write-Host "[4/4] Container status..."
Start-Sleep -Seconds 4
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "docker compose ps failed" }

Write-Host ""
Write-Host "============================================================"
Write-Host "MAP PATCH V2 GATE PASS"
Write-Host "Refresh GeoPilot once, then run ONE Full Track B Mission."
Write-Host "Urban should display automatically."
Write-Host "Use Urban / Rural buttons in the map HUD to switch context."
Write-Host "Backend AI and 7/7 acceptance logic were not modified."
Write-Host "============================================================"
