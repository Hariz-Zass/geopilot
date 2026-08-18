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
    <section className="gp2-projects">
      <header className="gp2-page-header">
        <div>
          <p className="eyebrow">Planning workspace</p>
          <h1>Projects</h1>
          <p className="gp2-muted">
            Select a planning project to continue.
          </p>
        </div>

        <span className="gp2-count">
          {projects.length} {projects.length === 1 ? "PROJECT" : "PROJECTS"}
        </span>
      </header>

      {error && (
        <div className="status-card status-error" role="alert">
          {error}
        </div>
      )}

      <section className="gp2-section">
        <div className="gp2-section-title">
          <h2>Existing Projects</h2>
        </div>

        {loading ? (
          <div className="gp2-empty">Loading projects...</div>
        ) : projects.length === 0 ? (
          <div className="gp2-empty">
            No projects available yet.
          </div>
        ) : (
          <div className="gp2-project-list">
            {projects.map((project) => (
              <article
                className="gp2-project-card"
                key={project.id}
              >
                <div className="gp2-project-icon">
                  GP
                </div>

                <div className="gp2-project-copy">
                  <strong>{project.name}</strong>

                  <p>
                    {project.description ||
                      "GeoPilot planning workspace"}
                  </p>
                </div>

                <Link
                  className="gp2-primary-link"
                  to={`/projects/${project.id}`}
                >
                  Open
                  <span aria-hidden="true">→</span>
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>

      <details className="gp2-details">
        <summary>
          <span>
            <strong>Create new project</strong>
            <small>Start another planning workspace</small>
          </span>

          <span aria-hidden="true">+</span>
        </summary>

        <form
          className="gp2-form"
          onSubmit={createProject}
        >
          <label>
            Project name
            <input
              value={name}
              onChange={(event) =>
                setName(event.target.value)
              }
              required
              maxLength={160}
            />
          </label>

          <label>
            Description
            <textarea
              value={description}
              onChange={(event) =>
                setDescription(event.target.value)
              }
              maxLength={5000}
            />
          </label>

          <button type="submit" disabled={busy}>
            {busy ? "Creating..." : "Create Project"}
          </button>
        </form>
      </details>
    </section>
  );
}
