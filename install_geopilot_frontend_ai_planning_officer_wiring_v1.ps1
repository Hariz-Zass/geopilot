$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Workspace = Join-Path $Root "frontend\src\features\planning\PlanningWorkspace.tsx"
if (!(Test-Path $Workspace)) {
    throw "PlanningWorkspace.tsx not found. Run this installer from the geopilot_v7 root."
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root "artifacts\frontend_ai_planning_officer_wiring_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Workspace (Join-Path $Backup "PlanningWorkspace.tsx")

Write-Host "============================================================"
Write-Host "GeoPilot Frontend AI Planning Officer Wiring V1"
Write-Host "Question -> PlanningRun create -> execute -> synthesis/evidence"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"
Write-Host ""

$patch = @'
from pathlib import Path

p = Path("/app/src/features/planning/PlanningWorkspace.tsx")
s = p.read_text(encoding="utf-8-sig")

old_imports = """import { sitesApi, type SiteResponse } from "../../lib/api/sites";
import { getSessionAccessToken } from "../../lib/auth/session";
import { PlanningMap } from "../map/PlanningMap";
"""
new_imports = """import { sitesApi, type SiteResponse } from "../../lib/api/sites";
import {
  planningRunsApi,
  type PlanningRunResponse,
} from "../../lib/api/planningRuns";
import { getSessionAccessToken } from "../../lib/auth/session";
import { PlanningMap } from "../map/PlanningMap";
"""
if old_imports not in s:
    raise SystemExit("BLOCKED: expected PlanningWorkspace import block not found.")
s = s.replace(old_imports, new_imports, 1)

old_state = """  const [question, setQuestion] = useState("");
  const [siteState, setSiteState] = useState<SiteState>({
    status: "loading",
  });
"""
new_state = """  const [question, setQuestion] = useState("");
  const [siteState, setSiteState] = useState<SiteState>({
    status: "loading",
  });
  const [analysisRun, setAnalysisRun] =
    useState<PlanningRunResponse | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<
    "idle" | "running" | "error"
  >("idle");
  const [analysisError, setAnalysisError] = useState<string | null>(
    null,
  );
"""
if old_state not in s:
    raise SystemExit("BLOCKED: expected PlanningWorkspace state block not found.")
s = s.replace(old_state, new_state, 1)

marker = """  }, [projectId, siteId]);

  return (
"""
handler = """  }, [projectId, siteId]);

  async function handlePrepareAnalysis() {
    const cleaned = question.trim();
    const token = getSessionAccessToken();

    if (!cleaned || !token || siteState.status !== "ready") {
      return;
    }

    setAnalysisStatus("running");
    setAnalysisError(null);
    setAnalysisRun(null);

    try {
      const created = await planningRunsApi.create(
        projectId,
        siteId,
        {
          question: cleaned,
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

      setAnalysisRun(executed);
      setAnalysisStatus("idle");
    } catch (error: unknown) {
      setAnalysisError(
        error instanceof Error
          ? error.message
          : "GeoPilot could not complete the planning analysis.",
      );
      setAnalysisStatus("error");
    }
  }

  return (
"""
if marker not in s:
    raise SystemExit("BLOCKED: expected handler insertion marker not found.")
s = s.replace(marker, handler, 1)

old_button = """          <button disabled={!question.trim()}>
            Prepare analysis
          </button>

          <p className="boundary-note">
            Evidence, limitations and professional review remain
            inspectable. GeoPilot does not grant statutory approval.
          </p>
"""
new_button = """          <button
            type="button"
            onClick={handlePrepareAnalysis}
            disabled={
              !question.trim() ||
              siteState.status !== "ready" ||
              analysisStatus === "running"
            }
          >
            {analysisStatus === "running"
              ? "Running analysis..."
              : "Prepare analysis"}
          </button>

          {analysisStatus === "running" && (
            <p role="status">
              GeoPilot is gathering validated evidence and running the
              Planning Officer.
            </p>
          )}

          {analysisError && (
            <div role="alert">{analysisError}</div>
          )}

          {analysisRun && (
            <section
              className="planning-analysis-result"
              aria-live="polite"
            >
              <h3>GeoPilot response</h3>

              <p>
                <strong>Status:</strong> {analysisRun.status}
              </p>

              {analysisRun.synthesis ? (
                <div className="planning-synthesis">
                  {analysisRun.synthesis
                    .split("\\n")
                    .filter(Boolean)
                    .map((line, index) => (
                      <p key={`${index}-${line.slice(0, 24)}`}>
                        {line}
                      </p>
                    ))}
                </div>
              ) : (
                <p>
                  No AI synthesis was produced. Validated evidence and
                  limitations remain available below.
                </p>
              )}

              <details>
                <summary>
                  Evidence ({analysisRun.evidence.length})
                </summary>
                <pre>
                  {JSON.stringify(
                    analysisRun.evidence,
                    null,
                    2,
                  )}
                </pre>
              </details>

              <details>
                <summary>
                  Limitations ({analysisRun.limitations.length})
                </summary>
                <pre>
                  {JSON.stringify(
                    analysisRun.limitations,
                    null,
                    2,
                  )}
                </pre>
              </details>

              {analysisRun.provider_metadata &&
                Object.keys(
                  analysisRun.provider_metadata,
                ).length > 0 && (
                  <details>
                    <summary>AI provider</summary>
                    <pre>
                      {JSON.stringify(
                        analysisRun.provider_metadata,
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                )}
            </section>
          )}

          <p className="boundary-note">
            Evidence, limitations and professional review remain
            inspectable. GeoPilot does not grant statutory approval.
          </p>
"""
if old_button not in s:
    raise SystemExit("BLOCKED: expected Prepare analysis button block not found.")
s = s.replace(old_button, new_button, 1)

p.write_text(s, encoding="utf-8")
print("PATCHED:", p)
'@

Write-Host "[1] Apply frontend wiring patch"
$patch | docker compose exec -T frontend python -
if ($LASTEXITCODE -ne 0) { throw "Frontend patch failed." }

Write-Host ""
Write-Host "[2] Show frontend package scripts"
docker compose exec -T frontend node -e "const p=require('./package.json'); console.log(p.scripts || {})"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect frontend package scripts." }

Write-Host ""
Write-Host "[3] TypeScript/Vite production build"
docker compose exec -T frontend npm run build
if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }

Write-Host ""
Write-Host "[4] Verify PlanningWorkspace wiring markers"
docker compose exec -T frontend node -e "const fs=require('fs'); const s=fs.readFileSync('/app/src/features/planning/PlanningWorkspace.tsx','utf8'); const required=['planningRunsApi.create','planningRunsApi.execute','GeoPilot response','analysisRun.synthesis']; for(const x of required){if(!s.includes(x)){throw new Error('Missing wiring marker: '+x)}} console.log('Frontend AI Planning Officer wiring markers: PASS')"
if ($LASTEXITCODE -ne 0) { throw "Frontend wiring verification failed." }

Write-Host ""
Write-Host "[5] Docker service health"
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "Docker service health check failed." }

Write-Host ""
Write-Host "============================================================"
Write-Host "FRONTEND AI PLANNING OFFICER WIRING V1 PASS"
Write-Host "============================================================"
Write-Host "Question submission: WIRED"
Write-Host "PlanningRun creation: WIRED"
Write-Host "PlanningRun execution: WIRED"
Write-Host "AI synthesis display: WIRED"
Write-Host "Evidence display: WIRED"
Write-Host "Limitations display: WIRED"
Write-Host "Backend terrain architecture changed: NO"
Write-Host "Database schema changed: NO"
Write-Host "Migration: NONE"
Write-Host "============================================================"
