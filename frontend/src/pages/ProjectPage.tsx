import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ApiError } from "../lib/api/errors";
import { projectsApi, type ProjectResponse } from "../lib/api/projects";
import { sitesApi, type SiteResponse } from "../lib/api/sites";
import { getSessionAccessToken } from "../lib/auth/session";

const geometryExample = `{
  "type": "Polygon",
  "coordinates": [
    [
      [101.7000, 3.0000],
      [101.7050, 3.0000],
      [101.7050, 3.0050],
      [101.7000, 3.0050],
      [101.7000, 3.0000]
    ]
  ]
}`;

export function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const token = getSessionAccessToken();
  const [project, setProject] = useState<ProjectResponse>();
  const [sites, setSites] = useState<SiteResponse[]>([]);
  const [siteName, setSiteName] = useState("Target Site");
  const [geometryText, setGeometryText] = useState(geometryExample);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    if (!token || !projectId) return;
    setLoading(true);
    setError(undefined);
    try {
      const [nextProject, nextSites] = await Promise.all([
        projectsApi.get(projectId, token),
        sitesApi.list(projectId, token),
      ]);
      setProject(nextProject);
      setSites(nextSites);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to load project.");
    } finally {
      setLoading(false);
    }
  }, [projectId, token]);

  useEffect(() => { void load(); }, [load]);

  if (!token) return <Navigate to="/login" replace />;
  if (!projectId) return <Navigate to="/projects" replace />;

  async function createSite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const geometry = JSON.parse(geometryText) as unknown;
      if (!token || !projectId) {
  setError("Project and authentication context are required.");
  setBusy(false);
  return;
}
      await sitesApi.create(projectId, { name: siteName, geometry, is_active: true }, token);
      await load();
    } catch (caught) {
      if (caught instanceof SyntaxError) {
        setError("Site geometry is not valid JSON.");
      } else {
        setError(caught instanceof ApiError ? caught.message : "Unable to create Site.");
      }
    } finally {
      setBusy(false);
    }
  }

  const activeSite = sites.find((site) => site.is_active && !site.is_archived);

  return (
    <section className="gp2-project-overview">
      <Link
        className="gp2-back"
        to="/projects"
      >
        ← Back to Projects
      </Link>

      <header className="gp2-project-hero gp-premium-project-hero">
        <div className="gp-premium-project-copy">
          <p className="eyebrow">
            Project workspace
          </p>

          <h1>
            GeoPilot AI Planning Workspace
          </h1>

          <div className="gp-final-project-identity">
            <span className="gp-final-project-identity-label">
              ACTIVE PROJECT
            </span>

            <strong className="gp-final-project-name">
              {loading
                ? "Loading project..."
                : (project?.name ?? "Planning Project")
                    .replace(/\s*Acceptance Test\s*/gi, "")
                    .trim()}
            </strong>
          </div>

          <p className="gp2-project-description">
            AI-powered geospatial planning workspace integrating
            spatial analysis, satellite intelligence, planning policy,
            and evidence-grounded decision support.
          </p>

          <div className="gp-premium-project-meta">
            <span>TRACK B</span>
            <span>GEOSPATIAL AI</span>
            <span>PLANNING DECISION SUPPORT</span>
          </div>
        </div>

        <aside className="gp-premium-status-panel">
          <div className="gp-premium-status-heading">
            <span className="gp-premium-status-dot" />
            <span>PROJECT STATUS</span>
          </div>

          <div className="gp-premium-status-main">
            <strong>
              {activeSite ? "Spatial Context Ready" : "Workspace Ready"}
            </strong>

            <span>
              {activeSite
                ? "Active study area connected"
                : "Study area not configured"}
            </span>
          </div>

          <div className="gp-premium-status-grid">
            <div>
              <small>PROJECT</small>
              <strong>ACTIVE</strong>
            </div>

            <div>
              <small>STUDY AREA</small>
              <strong>
                {activeSite ? "READY" : "PENDING"}
              </strong>
            </div>
          </div>

          <Link
            className="gp2-command gp-premium-command"
            to={`/projects/${projectId}/track-b`}
          >
            Open Command Center
            <span aria-hidden="true">→</span>
          </Link>
        </aside>
      </header>

      {error && (
        <div
          className="status-card status-error"
          role="alert"
        >
          {error}
        </div>
      )}

      <section className="gp2-action-grid">
        <Link
          className="gp2-action-card gp2-action-card-clickable"
          to={`/projects/${projectId}/documents`}
        >
          <span className="gp2-action-code">
            DOC
          </span>

          <h2>Planning Documents</h2>

          <p>
            Planning policy and supporting
            evidence for this project.
          </p>

          <span className="gp2-action-card-cta">
            Open Documents →
          </span>
        </Link>

        {activeSite ? (
          <Link
            className="gp2-action-card gp2-action-card-clickable"
            to={`/projects/${projectId}/map`}
          >
            <span className="gp2-action-code">
              SITE
            </span>

            <h2>Study Area</h2>

            <strong>{activeSite.name}</strong>

            <p>
              Active spatial boundary ·
              revision {activeSite.geometry_revision}
            </p>

            <span className="gp2-action-card-cta">
              Open Map →
            </span>
          </Link>
        ) : (
          <button
            type="button"
            className="gp2-action-card gp2-action-card-clickable gp2-action-card-button"
            onClick={() => {
              const setup = document.getElementById(
                "advanced-site-setup",
              ) as HTMLDetailsElement | null;

              if (setup) {
                setup.open = true;
                setup.scrollIntoView({
                  behavior: "smooth",
                  block: "center",
                });
              }
            }}
          >
            <span className="gp2-action-code">
              SITE
            </span>

            <h2>Study Area</h2>

            <p>
              No active study area configured.
            </p>

            <span className="gp2-action-card-cta">
              Add Study Area ↓
            </span>
          </button>
        )}
      </section>

      <details
        className="gp2-details gp2-site-details"
        id="advanced-site-setup"
      >
        <summary>
          <span>
            <strong>Advanced Site Setup</strong>

            <small>
              Create a study area using GeoJSON
            </small>
          </span>

          <span aria-hidden="true">+</span>
        </summary>

        <div className="gp2-site-intro">
          GeoJSON site creation is preserved for
          manual or fallback setup.
        </div>

        <form
          className="gp2-form"
          onSubmit={createSite}
        >
          <label>
            Site name

            <input
              value={siteName}
              onChange={(event) =>
                setSiteName(event.target.value)
              }
              required
            />
          </label>

          <label>
            GeoJSON Polygon / MultiPolygon

            <textarea
              className="code-input"
              value={geometryText}
              onChange={(event) =>
                setGeometryText(event.target.value)
              }
              required
            />
          </label>

          <button
            type="submit"
            disabled={busy}
          >
            {busy
              ? "Creating..."
              : "Create Active Site"}
          </button>
        </form>
      </details>
    </section>
  );
}
