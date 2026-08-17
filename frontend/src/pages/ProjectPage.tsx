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
    <section className="workspace-stack">
      <section className="panel">
        <p className="eyebrow">Project</p>
        <h1>{loading ? "Loading project..." : project?.name ?? "Project"}</h1>
        {project?.description && <p className="lede">{project.description}</p>}
        <p><Link to="/projects">Back to Projects</Link></p>
        <p>
          <Link to={`/projects/${projectId}/documents`}>
            Open Planning Documents
          </Link>
        </p>
        <p>
          <Link to={`/projects/${projectId}/track-b`} className="primary-link">Open Track B Command Center</Link>
        </p>
      </section>

      <section className="panel">
        <h2>Active Site</h2>
        {activeSite ? (
          <div className="resource-card">
            <div>
              <strong>{activeSite.name}</strong>
              <p>Geometry revision {activeSite.geometry_revision}</p>
            </div>
            <Link to={`/projects/${projectId}/map`}>Open Map</Link>
          </div>
        ) : (
          <p>No active Site yet. Create one below.</p>
        )}
      </section>

      <section className="panel">
        <h2>Create Site</h2>
        <p className="lede">For deployment testing, the textarea starts with an explicitly synthetic demo polygon. Replace it with your real project geometry later.</p>
        <form className="stack-form" onSubmit={createSite}>
          <label>Site name<input value={siteName} onChange={(e) => setSiteName(e.target.value)} required /></label>
          <label>GeoJSON Polygon / MultiPolygon<textarea className="code-input" value={geometryText} onChange={(e) => setGeometryText(e.target.value)} required /></label>
          <button type="submit" disabled={busy}>{busy ? "Creating..." : "Create Active Site"}</button>
        </form>
        {error && <div className="status-card status-error" role="alert">{error}</div>}
      </section>
    </section>
  );
}