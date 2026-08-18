$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Page = Join-Path $Root "frontend\src\pages\TrackBWorkspacePage.tsx"
if (!(Test-Path $Page)) {
    throw "TrackBWorkspacePage.tsx not found. Run from geopilot_v7 root."
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root "artifacts\trackb_decision_workspace_server_router_frontend_fix_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Page (Join-Path $Backup "TrackBWorkspacePage.tsx")

Write-Host "============================================================"
Write-Host "GeoPilot Track B Decision Workspace Frontend Fix V1"
Write-Host "Always call server-side decision-workspace router"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"
Write-Host ""

$text = Get-Content -Raw -Encoding UTF8 $Page

Write-Host "[1] Replace runPlannerDecision with server-routed version"

$pattern = '(?s)  async function runPlannerDecision\(\) \{.*?^  \}\r?\n\r?\n  async function openEvidenceReport\(\) \{'
$replacement = @'
  async function runPlannerDecision() {
    if (!projectId || !token || !result) {
      setError("Decision workspace is not ready: Project, authentication, or temporal analysis context is missing.");
      return;
    }

    if (!plannerQuestion.trim()) {
      setError("Enter a planner question before building the decision brief.");
      return;
    }

    setAiBusy(true);
    setError(undefined);

    try {
      // Server-side decision-workspace routing is authoritative.
      // Terrain questions are resolved by backend V2 to terrain.site_summary.
      // Temporal questions remain inside the Track B closed-evidence flow.
      const nextDecision = await trackBApi.decisionWorkspace(
        projectId,
        result.analysis_id,
        plannerQuestion.trim(),
        token,
      );

      setDecision(nextDecision);
      setTerrainPlanningRun(undefined);
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

  async function openEvidenceReport() {
'@

$newText = [regex]::Replace(
    $text,
    $pattern,
    $replacement,
    [System.Text.RegularExpressions.RegexOptions]::Multiline
)

if ($newText -eq $text) {
    throw "Expected runPlannerDecision block was not replaced."
}
$text = $newText

# Remove the now-unused frontend-only planningRuns import if present.
$text = $text -replace '(?ms)^import \{\s*planningRunsApi,\s*type PlanningRunResponse,\s*\} from "\.\./lib/api/planningRuns";\r?\n', ''

# If terrainPlanningRun state exists, keep the type import unnecessary by converting it to unknown-free removal.
$text = $text -replace '(?ms)^\s*// DECISION_WORKSPACE_TERRAIN_ROUTER_V1\r?\n\s*const \[terrainPlanningRun, setTerrainPlanningRun\] =\s*useState<PlanningRunResponse>\(\);\r?\n', '  const [terrainPlanningRun, setTerrainPlanningRun] = useState<any>();' + "`r`n"

Set-Content -Path $Page -Value $text -Encoding UTF8
Write-Host "PATCHED: frontend\src\pages\TrackBWorkspacePage.tsx"

Write-Host ""
Write-Host "[2] Production build"
docker compose exec -T frontend npm run build
if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }

Write-Host ""
Write-Host "[3] Verify no PlanningRun terrain call remains in TrackB Decision button"
$verify = Get-Content -Raw -Encoding UTF8 $Page
if ($verify.Contains("planningRunsApi.create") -or $verify.Contains("planningRunsApi.execute")) {
    throw "Frontend still contains PlanningRun calls in TrackBWorkspacePage."
}
if (-not $verify.Contains("trackBApi.decisionWorkspace")) {
    throw "TrackB decisionWorkspace call missing."
}
Write-Host "Frontend server-router dependency: PASS"

Write-Host ""
Write-Host "[4] Verify backend server terrain route still present"
docker compose exec -T backend python -c "import inspect; from app.api.v1.track_b import planner_decision_workspace; s=inspect.getsource(planner_decision_workspace); print('server_terrain_branch=', 'terrain_measurement' in s and 'build_track_b_terrain_planner_decision' in s); assert 'terrain_measurement' in s and 'build_track_b_terrain_planner_decision' in s"
if ($LASTEXITCODE -ne 0) { throw "Backend terrain-aware decision endpoint is missing." }

Write-Host ""
Write-Host "[5] Restart frontend"
docker compose restart frontend
if ($LASTEXITCODE -ne 0) { throw "Frontend restart failed." }
Start-Sleep -Seconds 4

Write-Host ""
Write-Host "[6] Service health"
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "Service health check failed." }

Write-Host ""
Write-Host "============================================================"
Write-Host "TRACK B DECISION WORKSPACE FRONTEND FIX V1 PASS"
Write-Host "============================================================"
Write-Host "Build decision brief button: SERVER ROUTER ONLY"
Write-Host "Inactive PlanningRun Site path: REMOVED"
Write-Host "Terrain question routing: BACKEND V2"
Write-Host "Terrain source: terrain.site_summary"
Write-Host "Temporal Track B flow: PRESERVED"
Write-Host "DB schema change: NONE"
Write-Host "Migration: NONE"
Write-Host "============================================================"
