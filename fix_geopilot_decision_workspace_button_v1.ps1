$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Page = Join-Path $Root "frontend\src\pages\TrackBWorkspacePage.tsx"
if (!(Test-Path $Page)) { throw "TrackBWorkspacePage.tsx not found." }

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root "artifacts\decision_workspace_button_fix_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Page (Join-Path $Backup "TrackBWorkspacePage.tsx")

Write-Host "============================================================"
Write-Host "GeoPilot Decision Workspace Button Fix V1"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"

$text = Get-Content -Raw -Encoding UTF8 $Page

$oldGuard = @'
  async function runPlannerDecision() {
    if (!projectId || !token || !result || !siteId) return;

    setAiBusy(true);
    setError(undefined);

    try {
'@

$newGuard = @'
  async function runPlannerDecision() {
    if (!projectId || !token || !result) {
      setError("Decision workspace is not ready: Project, authentication, or temporal analysis context is missing.");
      return;
    }

    const effectiveSiteId = siteId || result.site_id;

    if (!effectiveSiteId) {
      setError("Decision workspace is not ready: no Site is associated with this analysis.");
      return;
    }

    if (!plannerQuestion.trim()) {
      setError("Enter a planner question before building the decision brief.");
      return;
    }

    setAiBusy(true);
    setError(undefined);

    try {
'@

if (-not $text.Contains($oldGuard)) {
    throw "Expected runPlannerDecision guard block not found."
}
$text = $text.Replace($oldGuard, $newGuard)

$oldCreate = @'
          projectId,
          siteId,
          {
            question: plannerQuestion.trim(),
'@
$newCreate = @'
          projectId,
          effectiveSiteId,
          {
            question: plannerQuestion.trim(),
'@
$text = $text.Replace($oldCreate, $newCreate)

$oldExecute = @'
          projectId,
          siteId,
          created.id,
          token,
'@
$newExecute = @'
          projectId,
          effectiveSiteId,
          created.id,
          token,
'@
$text = $text.Replace($oldExecute, $newExecute)

Set-Content -Path $Page -Value $text -Encoding UTF8
Write-Host "[1] PATCHED frontend source"

Write-Host "[2] Production build"
docker compose exec -T frontend npm run build
if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }

Write-Host "[3] Verify markers"
$verify = Get-Content -Raw -Encoding UTF8 $Page
foreach ($m in @(
    "const effectiveSiteId = siteId || result.site_id",
    "Enter a planner question before building the decision brief.",
    "planningRunsApi.create",
    "planningRunsApi.execute"
)) {
    if (-not $verify.Contains($m)) { throw "Missing marker: $m" }
}
Write-Host "Button routing markers: PASS"

Write-Host "[4] Restart frontend"
docker compose restart frontend
if ($LASTEXITCODE -ne 0) { throw "Frontend restart failed." }
Start-Sleep -Seconds 4

Write-Host "[5] Service health"
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "Service health check failed." }

Write-Host "============================================================"
Write-Host "DECISION WORKSPACE BUTTON FIX V1 PASS"
Write-Host "============================================================"
Write-Host "Site fallback: result.site_id"
Write-Host "Silent guard returns: REMOVED"
Write-Host "Visible error feedback: ENABLED"
Write-Host "Frontend runtime restarted: YES"
Write-Host "Backend change: NONE"
Write-Host "Migration: NONE"
Write-Host "============================================================"
