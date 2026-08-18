$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Page = Join-Path $Root "frontend\src\pages\TrackBWorkspacePage.tsx"
if (!(Test-Path $Page)) {
    throw "TrackBWorkspacePage.tsx not found. Run from geopilot_v7 root."
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root "artifacts\trackb_decision_workspace_server_router_frontend_fix_v1_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Page (Join-Path $Backup "TrackBWorkspacePage.tsx")

Write-Host "============================================================"
Write-Host "GeoPilot Track B Decision Workspace Frontend Fix V1.1"
Write-Host "Recovery for PowerShell replace failure"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"
Write-Host ""

$text = Get-Content -Raw -Encoding UTF8 $Page

Write-Host "[1] Replace runPlannerDecision with authoritative server-routed version"

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
      // Backend V2 is the authoritative router:
      // terrain questions -> terrain.site_summary
      // temporal questions -> Track B closed-evidence decision flow
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
    if ($text.Contains("Backend V2 is the authoritative router")) {
        Write-Host "runPlannerDecision already server-routed; continuing."
    } else {
        throw "Expected runPlannerDecision block was not found."
    }
} else {
    $text = $newText
}

Write-Host ""
Write-Host "[2] Remove unused planningRunsApi value import but preserve PlanningRunResponse type"

$oldImport = @'
import {
  planningRunsApi,
  type PlanningRunResponse,
} from "../lib/api/planningRuns";
'@
$newImport = @'
import {
  type PlanningRunResponse,
} from "../lib/api/planningRuns";
'@

if ($text.Contains($oldImport)) {
    $text = $text.Replace($oldImport, $newImport)
} elseif ($text.Contains("planningRunsApi")) {
    throw "Unexpected planningRunsApi reference remains outside the known import block."
}

Set-Content -Path $Page -Value $text -Encoding UTF8
Write-Host "PATCHED: frontend\src\pages\TrackBWorkspacePage.tsx"

Write-Host ""
Write-Host "[3] Verify stale PlanningRun API calls are gone"
$verify = Get-Content -Raw -Encoding UTF8 $Page
if ($verify.Contains("planningRunsApi.create") -or $verify.Contains("planningRunsApi.execute")) {
    throw "Stale PlanningRun create/execute calls remain."
}
if (-not $verify.Contains("trackBApi.decisionWorkspace")) {
    throw "Server-side decisionWorkspace call is missing."
}
if (-not $verify.Contains("Backend V2 is the authoritative router")) {
    throw "Server-router marker is missing."
}
Write-Host "Frontend server-router source verification: PASS"

Write-Host ""
Write-Host "[4] Production build"
docker compose exec -T frontend npm run build
if ($LASTEXITCODE -ne 0) {
    throw "Frontend production build failed."
}

Write-Host ""
Write-Host "[5] Verify backend V2 terrain branch"
docker compose exec -T backend python -c "import inspect; from app.api.v1.track_b import planner_decision_workspace; s=inspect.getsource(planner_decision_workspace); print('server_terrain_branch=', 'terrain_measurement' in s and 'build_track_b_terrain_planner_decision' in s); assert 'terrain_measurement' in s and 'build_track_b_terrain_planner_decision' in s"
if ($LASTEXITCODE -ne 0) {
    throw "Backend terrain-aware decision endpoint is missing."
}

Write-Host ""
Write-Host "[6] Restart frontend"
docker compose restart frontend
if ($LASTEXITCODE -ne 0) {
    throw "Frontend restart failed."
}
Start-Sleep -Seconds 4

Write-Host ""
Write-Host "[7] Service health"
docker compose ps
if ($LASTEXITCODE -ne 0) {
    throw "Service health check failed."
}

Write-Host ""
Write-Host "============================================================"
Write-Host "TRACK B DECISION WORKSPACE FRONTEND FIX V1.1 PASS"
Write-Host "============================================================"
Write-Host "Build decision brief button: SERVER ROUTER ONLY"
Write-Host "Inactive PlanningRun Site path: REMOVED"
Write-Host "Terrain question routing: BACKEND V2"
Write-Host "Terrain source: terrain.site_summary"
Write-Host "Temporal Track B flow: PRESERVED"
Write-Host "DB schema change: NONE"
Write-Host "Migration: NONE"
Write-Host "============================================================"
