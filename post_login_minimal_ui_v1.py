from pathlib import Path
import shutil
import subprocess
import datetime
import sys

ROOT = Path.cwd()

projects_file = ROOT / "frontend/src/pages/ProjectsPage.tsx"
project_file = ROOT / "frontend/src/pages/ProjectPage.tsx"
css_file = ROOT / "frontend/src/styles.css"

stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

artifacts = ROOT / "artifacts"
backup = artifacts / f"post_login_minimal_ui_v1_backup_{stamp}"
log = artifacts / f"post_login_minimal_ui_v1_{stamp}.txt"

artifacts.mkdir(exist_ok=True)
backup.mkdir(exist_ok=True)

def write_log(text=""):
    print(text)
    with log.open("a", encoding="utf-8") as f:
        f.write(str(text) + "\n")

def run(cmd):
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    write_log(result.stdout)
    return result.returncode

write_log("=" * 68)
write_log("GEOPILOT POST-LOGIN MINIMAL UI V1")
write_log("PRESENTATION ONLY / FUNCTION PRESERVED")
write_log("=" * 68)

success = False

try:
    # ---------------------------------------------------------
    # BACKUP CURRENT ACCEPTED STATE
    # ---------------------------------------------------------

    shutil.copy2(projects_file, backup / "ProjectsPage.tsx")
    shutil.copy2(project_file, backup / "ProjectPage.tsx")
    shutil.copy2(css_file, backup / "styles.css")

    write_log(f"BACKUP = {backup}")

    projects = projects_file.read_text(encoding="utf-8-sig")
    project = project_file.read_text(encoding="utf-8-sig")
    css = css_file.read_text(encoding="utf-8-sig")

    # ---------------------------------------------------------
    # PROJECTS PAGE - REPLACE PRESENTATION RETURN ONLY
    # ---------------------------------------------------------

    projects_return_start = projects.index("  return (")

    new_projects_return = r'''  return (
    <section className="gp-project-hub">
      <header className="gp-project-hub-header">
        <div>
          <p className="eyebrow">Planning workspace</p>
          <h1>Projects</h1>
          <p className="gp-project-hub-copy">
            Open an existing planning workspace or create a new one.
          </p>
        </div>

        <div className="gp-project-count">
          <strong>{projects.length}</strong>
          <span>{projects.length === 1 ? "project" : "projects"}</span>
        </div>
      </header>

      {error && (
        <div className="status-card status-error" role="alert">
          {error}
        </div>
      )}

      <section className="gp-project-section">
        <div className="gp-project-section-heading">
          <div>
            <p className="eyebrow">Your workspaces</p>
            <h2>Existing Projects</h2>
          </div>
        </div>

        {loading ? (
          <div className="gp-project-empty">Loading projects...</div>
        ) : projects.length === 0 ? (
          <div className="gp-project-empty">
            No projects yet. Create your first project below.
          </div>
        ) : (
          <div className="gp-project-list">
            {projects.map((project) => (
              <article className="gp-project-card" key={project.id}>
                <div className="gp-project-card-mark" aria-hidden="true">
                  GP
                </div>

                <div className="gp-project-card-copy">
                  <strong>{project.name}</strong>
                  <p>
                    {project.description ||
                      "Planning workspace with no description."}
                  </p>

                  <div className="gp-project-card-meta">
                    <span>PLANNING PROJECT</span>
                    <span>GEOPILOT</span>
                  </div>
                </div>

                <Link
                  className="gp-project-open"
                  to={`/projects/${project.id}`}
                >
                  Open Project
                  <span aria-hidden="true">→</span>
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>

      <details className="gp-project-create">
        <summary>
          <span>
            <strong>Create new project</strong>
            <small>Start another GeoPilot planning workspace</small>
          </span>
          <span aria-hidden="true">+</span>
        </summary>

        <form
          className="gp-project-create-form"
          onSubmit={createProject}
        >
          <label>
            Project name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={160}
              placeholder="Example: Shah Alam Planning Review"
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
              placeholder="Optional project description"
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
'''

    projects = projects[:projects_return_start] + new_projects_return

    # ---------------------------------------------------------
    # PROJECT PAGE - REPLACE PRESENTATION RETURN ONLY
    # ---------------------------------------------------------

    project_return_start = project.index("  return (")

    new_project_return = r'''  return (
    <section className="gp-project-overview">
      <Link className="gp-project-back" to="/projects">
        ← Projects
      </Link>

      <header className="gp-project-overview-hero">
        <div className="gp-project-overview-copy">
          <p className="eyebrow">Project workspace</p>

          <h1>
            {loading
              ? "Loading project..."
              : project?.name ?? "Project"}
          </h1>

          {project?.description && (
            <p>{project.description}</p>
          )}
        </div>

        <Link
          to={`/projects/${projectId}/track-b`}
          className="gp-project-command-button"
        >
          Open Command Center
          <span aria-hidden="true">→</span>
        </Link>
      </header>

      {error && (
        <div className="status-card status-error" role="alert">
          {error}
        </div>
      )}

      <section className="gp-project-quick-grid">
        <article className="gp-project-quick-card">
          <div className="gp-project-quick-icon">DOC</div>

          <div>
            <p className="eyebrow">Planning evidence</p>
            <h2>Planning Documents</h2>
            <p>
              Manage policy and planning evidence used by GeoPilot.
            </p>
          </div>

          <Link to={`/projects/${projectId}/documents`}>
            Open Documents →
          </Link>
        </article>

        <article className="gp-project-quick-card">
          <div className="gp-project-quick-icon">SITE</div>

          <div>
            <p className="eyebrow">Spatial context</p>
            <h2>Active Site</h2>

            {activeSite ? (
              <>
                <strong>{activeSite.name}</strong>
                <p>
                  Geometry revision {activeSite.geometry_revision}
                </p>
              </>
            ) : (
              <p>No active site configured yet.</p>
            )}
          </div>

          {activeSite ? (
            <Link to={`/projects/${projectId}/map`}>
              Open Map →
            </Link>
          ) : (
            <a href="#manual-site-setup">
              Configure Site ↓
            </a>
          )}
        </article>
      </section>

      <details
        className="gp-project-site-setup"
        id="manual-site-setup"
      >
        <summary>
          <span>
            <strong>Manual / advanced site setup</strong>
            <small>Create an active site from GeoJSON</small>
          </span>
          <span aria-hidden="true">+</span>
        </summary>

        <div className="gp-project-site-setup-body">
          <p>
            The demo geometry is synthetic. Replace it with the real
            project boundary when required.
          </p>

          <form
            className="gp-project-site-form"
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

            <button type="submit" disabled={busy}>
              {busy ? "Creating..." : "Create Active Site"}
            </button>
          </form>
        </div>
      </details>
    </section>
  );
}
'''

    project = project[:project_return_start] + new_project_return

    # ---------------------------------------------------------
    # FUNCTION CONTRACT CHECK BEFORE WRITE
    # ---------------------------------------------------------

    contracts = [
        (projects, "projectsApi.list(token)"),
        (projects, "projectsApi.create("),
        (project, "projectsApi.get(projectId, token)"),
        (project, "sitesApi.list(projectId, token)"),
        (project, "sitesApi.create("),
        (project, "/documents"),
        (project, "/track-b"),
        (project, "/map"),
    ]

    for source, token in contracts:
        if token not in source:
            raise RuntimeError(
                f"Functional contract missing: {token}"
            )

    write_log("FUNCTIONAL_CONTRACT_CHECK = PASS")

    projects_file.write_text(
        projects,
        encoding="utf-8",
        newline="\n",
    )

    project_file.write_text(
        project,
        encoding="utf-8",
        newline="\n",
    )

    # ---------------------------------------------------------
    # SCOPED CSS
    # ---------------------------------------------------------

    marker = "/* GEOPILOT POST-LOGIN MINIMAL UI V1 */"

    if marker not in css:
        css += r'''

/* GEOPILOT POST-LOGIN MINIMAL UI V1 */

.gp-project-hub,
.gp-project-overview {
  width: min(1080px, calc(100% - 2rem));
  margin: 0 auto;
  padding: 3rem 0 4.5rem;
}

.gp-project-hub-header,
.gp-project-overview-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 2rem;
  margin-bottom: 1.8rem;
}

.gp-project-hub-header h1,
.gp-project-overview-hero h1 {
  margin: .2rem 0 .55rem;
  color: #071827;
  font-size: clamp(2.4rem, 4vw, 3.6rem);
  line-height: 1;
  letter-spacing: -.045em;
}

.gp-project-hub-copy,
.gp-project-overview-copy > p:last-child {
  max-width: 720px;
  margin: 0;
  color: #65798b;
}

.gp-project-count {
  min-width: 105px;
  padding: .85rem 1rem;
  border: 1px solid #dfe8ef;
  border-radius: 12px;
  background: #fff;
  text-align: right;
}

.gp-project-count strong,
.gp-project-count span {
  display: block;
}

.gp-project-count strong {
  color: #071827;
  font-size: 1.5rem;
}

.gp-project-count span {
  color: #82909d;
  font-size: .65rem;
  text-transform: uppercase;
  letter-spacing: .08em;
}

.gp-project-section-heading {
  margin-bottom: .75rem;
}

.gp-project-section-heading h2 {
  margin: .2rem 0 0;
  font-size: 1.25rem;
}

.gp-project-list {
  display: grid;
  gap: .7rem;
}

.gp-project-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: .9rem;
  padding: .95rem 1rem;
  border: 1px solid #dfe8ef;
  border-radius: 14px;
  background: #fff;
}

.gp-project-card-mark {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: #071827;
  color: #58f5df;
  font-size: .68rem;
  font-weight: 850;
}

.gp-project-card-copy strong {
  color: #071827;
}

.gp-project-card-copy p {
  margin: .2rem 0 .45rem;
  color: #687b8d;
  font-size: .8rem;
  line-height: 1.45;
}

.gp-project-card-meta {
  display: flex;
  gap: .4rem;
}

.gp-project-card-meta span {
  padding: .18rem .38rem;
  border-radius: 5px;
  background: #eef5f6;
  color: #3b706c;
  font-size: .55rem;
  font-weight: 800;
  letter-spacing: .06em;
}

.gp-project-open,
.gp-project-command-button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .8rem;
  border-radius: 9px;
  background: #071827;
  color: #fff;
  text-decoration: none;
  font-size: .76rem;
  font-weight: 800;
}

.gp-project-open {
  min-width: 130px;
  padding: .7rem .8rem;
}

.gp-project-command-button {
  min-width: 210px;
  padding: .9rem 1rem;
}

.gp-project-open span,
.gp-project-command-button span {
  color: #58f5df;
}

.gp-project-empty {
  padding: 1.6rem;
  border: 1px dashed #cedae4;
  border-radius: 13px;
  text-align: center;
  color: #6d7e8d;
}

.gp-project-create,
.gp-project-site-setup {
  margin-top: .9rem;
  border: 1px solid #dfe8ef;
  border-radius: 13px;
  background: #fff;
  overflow: hidden;
}

.gp-project-create summary,
.gp-project-site-setup summary {
  min-height: 64px;
  padding: .9rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  list-style: none;
}

.gp-project-create summary::-webkit-details-marker,
.gp-project-site-setup summary::-webkit-details-marker {
  display: none;
}

.gp-project-create summary strong,
.gp-project-create summary small,
.gp-project-site-setup summary strong,
.gp-project-site-setup summary small {
  display: block;
}

.gp-project-create summary small,
.gp-project-site-setup summary small {
  margin-top: .12rem;
  color: #7b8b99;
}

.gp-project-create-form,
.gp-project-site-form {
  padding: 1rem;
  display: grid;
  gap: .9rem;
  border-top: 1px solid #e6edf2;
}

.gp-project-create-form label,
.gp-project-site-form label {
  display: grid;
  gap: .4rem;
  font-size: .76rem;
  font-weight: 800;
}

.gp-project-create-form input,
.gp-project-create-form textarea,
.gp-project-site-form input,
.gp-project-site-form textarea {
  border: 1px solid #d6e0e8;
  border-radius: 8px;
  padding: .75rem .8rem;
  background: #fff;
  font: inherit;
}

.gp-project-create-form textarea {
  min-height: 80px;
}

.gp-project-site-form textarea {
  min-height: 220px;
}

.gp-project-create-form button,
.gp-project-site-form button {
  min-height: 44px;
  border: 0;
  border-radius: 8px;
  background: #071827;
  color: #fff;
  font: inherit;
  font-weight: 800;
}

.gp-project-back {
  display: inline-block;
  margin-bottom: 1rem;
  color: #587181;
  text-decoration: none;
  font-size: .8rem;
  font-weight: 700;
}

.gp-project-quick-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .8rem;
}

.gp-project-quick-card {
  min-height: 205px;
  padding: 1rem;
  display: grid;
  grid-template-rows: auto 1fr auto;
  border: 1px solid #dfe8ef;
  border-radius: 14px;
  background: #fff;
}

.gp-project-quick-icon {
  width: fit-content;
  margin-bottom: .8rem;
  padding: .3rem .45rem;
  border: 1px solid #c8ebe5;
  border-radius: 6px;
  color: #118d80;
  font-size: .58rem;
  font-weight: 850;
}

.gp-project-quick-card h2 {
  margin: .15rem 0 .4rem;
  font-size: 1.18rem;
}

.gp-project-quick-card p {
  margin: .15rem 0;
  color: #697b8c;
  font-size: .8rem;
}

.gp-project-quick-card > a {
  margin-top: .8rem;
  color: #087f73;
  font-size: .78rem;
  font-weight: 800;
  text-decoration: none;
}

.gp-project-site-setup-body > p {
  margin: .9rem 1rem 0;
  color: #718191;
  font-size: .8rem;
}

@media (max-width: 760px) {
  .gp-project-hub,
  .gp-project-overview {
    width: min(100% - 1.2rem, 1080px);
    padding-top: 2rem;
  }

  .gp-project-hub-header,
  .gp-project-overview-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .gp-project-card {
    grid-template-columns: auto 1fr;
  }

  .gp-project-open {
    grid-column: 1 / -1;
  }

  .gp-project-quick-grid {
    grid-template-columns: 1fr;
  }

  .gp-project-command-button {
    width: 100%;
  }
}
'''

        css_file.write_text(
            css,
            encoding="utf-8",
            newline="\n",
        )

    write_log("PATCH_APPLIED = YES")

    # ---------------------------------------------------------
    # TEST
    # ---------------------------------------------------------

    write_log("")
    write_log("=== FRONTEND TEST ===")

    test_exit = run([
        "docker",
        "compose",
        "exec",
        "-T",
        "frontend",
        "npm",
        "test",
        "--",
        "--run",
    ])

    write_log(f"TEST_EXIT_CODE = {test_exit}")

    if test_exit != 0:
        raise RuntimeError("Frontend tests failed.")

    # ---------------------------------------------------------
    # BUILD
    # ---------------------------------------------------------

    write_log("")
    write_log("=== FRONTEND BUILD ===")

    build_exit = run([
        "docker",
        "compose",
        "exec",
        "-T",
        "frontend",
        "npm",
        "run",
        "build",
    ])

    write_log(f"BUILD_EXIT_CODE = {build_exit}")

    if build_exit != 0:
        raise RuntimeError("Frontend build failed.")

    write_log("")
    write_log("POST_LOGIN_MINIMAL_UI_V1 = PASS")
    write_log("BACKEND_WRITE = NONE")
    write_log("DATABASE_WRITE = NONE")

    success = True

except Exception as exc:
    write_log("")
    write_log("POST_LOGIN_MINIMAL_UI_V1 = ERROR")
    write_log(f"ERROR = {exc!r}")

finally:
    if not success:
        shutil.copy2(
            backup / "ProjectsPage.tsx",
            projects_file,
        )
        shutil.copy2(
            backup / "ProjectPage.tsx",
            project_file,
        )
        shutil.copy2(
            backup / "styles.css",
            css_file,
        )

        write_log("AUTO_RESTORE = COMPLETE")

    write_log("")
    write_log(f"LOG = {log}")
    write_log("LOG_CAPTURE = COMPLETE")

    print("")
    print("RESULT SAVED TO:")
    print(log)

sys.exit(0 if success else 1)
