import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { ApiError } from "../lib/api/errors";
import { projectsApi, type ProjectResponse } from "../lib/api/projects";
import { getSessionAccessToken } from "../lib/auth/session";

export function ProjectsPage() {
  const token = getSessionAccessToken();
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(undefined);
    try {
      setProjects(await projectsApi.list(token));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to load projects.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { void load(); }, [load]);

  if (!token) return <Navigate to="/login" replace />;

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
	if (!token) {
  setError("Authentication is required.");
  setBusy(false);
  return;
}
      await projectsApi.create({ name, description: description.trim() || null }, token);
      setName("");
      setDescription("");
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to create project.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="workspace-stack">
      <section className="panel">
        <p className="eyebrow">Projects</p>
        <h1>Your planning projects</h1>
        <form className="stack-form" onSubmit={createProject}>
          <label>Project name<input value={name} onChange={(e) => setName(e.target.value)} required maxLength={160} /></label>
          <label>Description<textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={5000} /></label>
          <button type="submit" disabled={busy}>{busy ? "Creating..." : "Create Project"}</button>
        </form>
        {error && <div className="status-card status-error" role="alert">{error}</div>}
      </section>

      <section className="panel">
        <h2>Existing Projects</h2>
        {loading ? <p>Loading...</p> : projects.length === 0 ? <p>No projects yet.</p> : (
          <div className="card-list">
            {projects.map((project) => (
              <article className="resource-card" key={project.id}>
                <div>
                  <strong>{project.name}</strong>
                  <p>{project.description || "No description"}</p>
                </div>
                <Link to={`/projects/${project.id}`}>Open</Link>
              </article>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}