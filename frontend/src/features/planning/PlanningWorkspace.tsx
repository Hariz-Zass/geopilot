import { useEffect, useState } from "react";

import { sitesApi, type SiteResponse } from "../../lib/api/sites";
import {
  planningRunsApi,
  type PlanningRunResponse,
} from "../../lib/api/planningRuns";
import { getSessionAccessToken } from "../../lib/auth/session";
import { PlanningMap } from "../map/PlanningMap";

type PlanningWorkspaceProps = {
  projectId: string;
  siteId: string;
};

type SiteState =
  | { status: "loading" }
  | { status: "unauthenticated" }
  | { status: "ready"; site: SiteResponse }
  | { status: "error"; message: string };

export function PlanningWorkspace({
  projectId,
  siteId,
}: PlanningWorkspaceProps) {
  const [question, setQuestion] = useState("");
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

  useEffect(() => {
    const token = getSessionAccessToken();

    if (!token) {
      setSiteState({
        status: "unauthenticated",
      });
      return;
    }

    let active = true;

    setSiteState({
      status: "loading",
    });

    sitesApi
      .active(projectId, token)
      .then((site) => {
        if (!active) {
          return;
        }

        if (site.id !== siteId) {
          setSiteState({
            status: "error",
            message:
              "The requested Site is not the server-designated active Site for this Project.",
          });
          return;
        }

        setSiteState({
          status: "ready",
          site,
        });
      })
      .catch((error: unknown) => {
        if (!active) {
          return;
        }

        setSiteState({
          status: "error",
          message:
            error instanceof Error
              ? error.message
              : "The active Site could not be loaded.",
        });
      });

    return () => {
      active = false;
    };
  }, [projectId, siteId]);

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
    <main className="planning-workspace">
      <header>
        <h1>GeoPilot AI Planning Workspace</h1>
        <p>
          Project and Site context are required before analysis.
        </p>
      </header>

      <section className="planning-grid">
        <div className="planning-map-panel">
          {siteState.status === "loading" && (
            <p role="status">Loading active Site...</p>
          )}

          {siteState.status === "unauthenticated" && (
            <div role="alert">
              Authentication is required before loading Project
              evidence.
            </div>
          )}

          {siteState.status === "error" && (
            <div role="alert">{siteState.message}</div>
          )}

          {siteState.status === "ready" && (
            <PlanningMap site={siteState.site} />
          )}
        </div>

        <aside className="planning-officer-panel">
          <h2>AI Planning Officer</h2>

          <label>
            Planning question
            <textarea
              value={question}
              onChange={(event) =>
                setQuestion(event.target.value)
              }
              placeholder="Ask an evidence-bounded planning question"
            />
          </label>

          <button
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
                    .split("\n")
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
        </aside>
      </section>
    </main>
  );
}
