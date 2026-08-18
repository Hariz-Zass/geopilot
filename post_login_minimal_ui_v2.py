from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime

ROOT = Path.cwd()

projects_file = ROOT / "frontend/src/pages/ProjectsPage.tsx"
project_file = ROOT / "frontend/src/pages/ProjectPage.tsx"
css_file = ROOT / "frontend/src/styles.css"

artifact_dir = ROOT / "artifacts"
artifact_dir.mkdir(exist_ok=True)

log = artifact_dir / "post_login_minimal_ui_v2.txt"
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = artifact_dir / f"post_login_minimal_ui_v2_backup_{stamp}"
backup.mkdir(exist_ok=True)

def logline(text=""):
    print(text)
    with log.open("a", encoding="utf-8") as f:
        f.write(str(text) + "\n")

def run(cmd):
    p = subprocess.run(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    logline(p.stdout)
    return p.returncode

def replace_final_return(source, replacement):
    marker = "  return ("
    pos = source.rfind(marker)

    if pos < 0:
        raise RuntimeError("Final JSX return block not found.")

    return source[:pos] + replacement.rstrip() + "\n"

log.write_text(
    "============================================================\n"
    "GEOPILOT POST-LOGIN MINIMAL UI V2\n"
    "FRONTEND PRESENTATION ONLY\n"
    "============================================================\n",
    encoding="utf-8",
)

success = False

try:
    # ---------------------------------------------------------
    # BACKUP
    # ---------------------------------------------------------

    shutil.copy2(projects_file, backup / "ProjectsPage.tsx")
    shutil.copy2(project_file, backup / "ProjectPage.tsx")
    shutil.copy2(css_file, backup / "styles.css")

    logline(f"BACKUP = {backup}")

    projects = projects_file.read_text(encoding="utf-8-sig")
    project = project_file.read_text(encoding="utf-8-sig")
    css = css_file.read_text(encoding="utf-8-sig")

    # ---------------------------------------------------------
    # FUNCTION SAFETY BEFORE PATCH
    # ---------------------------------------------------------

    required_before = [
        (projects, "projectsApi.list(token)"),
        (projects, "projectsApi.create("),
        (project, "projectsApi.get(projectId, token)"),
        (project, "sitesApi.list(projectId, token)"),
        (project, "sitesApi.create("),
    ]

    for source, token in required_before:
        if token not in source:
            raise RuntimeError(
                f"Pre-patch function missing: {token}"
            )

    logline("PRE_PATCH_FUNCTION_CHECK = PASS")

    # ---------------------------------------------------------
    # PROJECTS PAGE
    # ---------------------------------------------------------

    projects_return = """  return (
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
"""

    projects = replace_final_return(
        projects,
        projects_return,
    )

    # ---------------------------------------------------------
    # PROJECT OVERVIEW
    # ---------------------------------------------------------

    project_return = """  return (
    <section className="gp2-project-overview">
      <Link
        className="gp2-back"
        to="/projects"
      >
        ← Back to Projects
      </Link>

      <header className="gp2-project-hero">
        <div>
          <p className="eyebrow">
            Project workspace
          </p>

          <h1>
            {loading
              ? "Loading project..."
              : project?.name ?? "Project"}
          </h1>

          {project?.description && (
            <p className="gp2-project-description">
              {project.description}
            </p>
          )}
        </div>

        <Link
          className="gp2-command"
          to={`/projects/${projectId}/track-b`}
        >
          Open Command Center
          <span aria-hidden="true">→</span>
        </Link>
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
        <article className="gp2-action-card">
          <span className="gp2-action-code">
            DOC
          </span>

          <h2>Planning Documents</h2>

          <p>
            Planning policy and supporting
            evidence for this project.
          </p>

          <Link
            to={`/projects/${projectId}/documents`}
          >
            Open Documents →
          </Link>
        </article>

        <article className="gp2-action-card">
          <span className="gp2-action-code">
            SITE
          </span>

          <h2>Study Area</h2>

          {activeSite ? (
            <>
              <strong>{activeSite.name}</strong>

              <p>
                Active spatial boundary ·
                revision {activeSite.geometry_revision}
              </p>

              <Link
                to={`/projects/${projectId}/map`}
              >
                Open Map →
              </Link>
            </>
          ) : (
            <>
              <p>
                No active study area configured.
              </p>

              <a href="#advanced-site-setup">
                Add Study Area ↓
              </a>
            </>
          )}
        </article>
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
"""

    project = replace_final_return(
        project,
        project_return,
    )

    # ---------------------------------------------------------
    # POST PATCH CONTRACT CHECK
    # ---------------------------------------------------------

    required_after = [
        (projects, "projectsApi.list(token)"),
        (projects, "projectsApi.create("),
        (project, "projectsApi.get(projectId, token)"),
        (project, "sitesApi.list(projectId, token)"),
        (project, "sitesApi.create("),
        (project, "/documents"),
        (project, "/track-b"),
        (project, "/map"),
    ]

    for source, token in required_after:
        if token not in source:
            raise RuntimeError(
                f"Post-patch function missing: {token}"
            )

    logline("POST_PATCH_FUNCTION_CHECK = PASS")

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
    # CSS
    # ---------------------------------------------------------

    marker = "/* GEOPILOT POST LOGIN MINIMAL UI V2 */"

    if marker not in css:
        css += """

/* GEOPILOT POST LOGIN MINIMAL UI V2 */

.gp2-projects,
.gp2-project-overview {
  width: min(1040px, calc(100% - 2rem));
  margin: 0 auto;
  padding: 3rem 0 4rem;
}

.gp2-page-header,
.gp2-project-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 2rem;
  margin-bottom: 1.75rem;
}

.gp2-page-header h1,
.gp2-project-hero h1 {
  margin: .2rem 0 .55rem;
  color: #071827;
  font-size: clamp(2.3rem, 4vw, 3.5rem);
  line-height: 1;
  letter-spacing: -.04em;
}

.gp2-muted,
.gp2-project-description {
  max-width: 700px;
  margin: 0;
  color: #677b8c;
  line-height: 1.55;
}

.gp2-count {
  padding: .55rem .75rem;
  border: 1px solid #dce7ed;
  border-radius: 8px;
  background: #fff;
  color: #6f8392;
  font-size: .64rem;
  font-weight: 800;
  letter-spacing: .08em;
}

.gp2-section-title {
  margin-bottom: .7rem;
}

.gp2-section-title h2 {
  margin: 0;
  font-size: 1.18rem;
}

.gp2-project-list {
  display: grid;
  gap: .65rem;
}

.gp2-project-card {
  display: grid;
  grid-template-columns:
    auto minmax(0, 1fr) auto;

  align-items: center;
  gap: .9rem;

  padding: .9rem 1rem;

  border: 1px solid #dce7ed;
  border-radius: 12px;

  background: #fff;
}

.gp2-project-icon {
  width: 38px;
  height: 38px;

  display: grid;
  place-items: center;

  border-radius: 9px;

  background: #071827;
  color: #58f5df;

  font-size: .65rem;
  font-weight: 900;
}

.gp2-project-copy strong {
  color: #071827;
  font-size: .95rem;
}

.gp2-project-copy p {
  margin: .2rem 0 0;

  color: #6b7f90;

  font-size: .78rem;
  line-height: 1.45;
}

.gp2-primary-link,
.gp2-command {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: .8rem;

  background: #071827;
  color: #fff;

  border-radius: 8px;

  text-decoration: none;

  font-size: .75rem;
  font-weight: 850;
}

.gp2-primary-link {
  min-width: 105px;
  padding: .68rem .75rem;
}

.gp2-command {
  min-width: 205px;
  padding: .85rem .95rem;
}

.gp2-primary-link span,
.gp2-command span {
  color: #58f5df;
}

.gp2-empty {
  padding: 1.5rem;

  border: 1px dashed #cedbe4;
  border-radius: 11px;

  color: #718392;
  text-align: center;
}

.gp2-details {
  margin-top: .8rem;

  border: 1px solid #dce7ed;
  border-radius: 11px;

  background: #fff;

  overflow: hidden;
}

.gp2-details summary {
  min-height: 60px;

  padding: .85rem 1rem;

  display: flex;
  align-items: center;
  justify-content: space-between;

  cursor: pointer;
  list-style: none;
}

.gp2-details summary::-webkit-details-marker {
  display: none;
}

.gp2-details summary strong,
.gp2-details summary small {
  display: block;
}

.gp2-details summary strong {
  color: #071827;
  font-size: .86rem;
}

.gp2-details summary small {
  margin-top: .1rem;

  color: #7c8e9b;
  font-size: .68rem;
}

.gp2-details summary > span:last-child {
  color: #168f82;
  font-size: 1.15rem;
}

.gp2-form {
  padding: 1rem;

  display: grid;
  gap: .85rem;

  border-top: 1px solid #e4edf2;
}

.gp2-form label {
  display: grid;
  gap: .4rem;

  color: #172c3c;

  font-size: .75rem;
  font-weight: 800;
}

.gp2-form input,
.gp2-form textarea {
  border: 1px solid #d4dfe7;
  border-radius: 8px;

  padding: .72rem .8rem;

  background: #fff;
  color: #071827;

  font: inherit;
}

.gp2-form textarea {
  min-height: 100px;
}

.gp2-site-details .code-input {
  min-height: 220px;
}

.gp2-form button {
  min-height: 43px;

  border: 0;
  border-radius: 8px;

  background: #071827;
  color: #fff;

  font: inherit;
  font-weight: 850;

  cursor: pointer;
}

.gp2-back {
  display: inline-block;

  margin-bottom: .9rem;

  color: #587283;

  text-decoration: none;

  font-size: .78rem;
  font-weight: 750;
}

.gp2-action-grid {
  display: grid;
  grid-template-columns:
    repeat(2, minmax(0, 1fr));

  gap: .75rem;
}

.gp2-action-card {
  min-height: 190px;

  padding: 1rem;

  display: flex;
  flex-direction: column;

  border: 1px solid #dce7ed;
  border-radius: 12px;

  background: #fff;
}

.gp2-action-code {
  width: fit-content;

  padding: .26rem .4rem;

  border: 1px solid #c9e9e4;
  border-radius: 5px;

  color: #108d80;

  font-size: .56rem;
  font-weight: 900;
}

.gp2-action-card h2 {
  margin: .8rem 0 .35rem;

  color: #071827;

  font-size: 1.15rem;
}

.gp2-action-card p {
  margin: 0;

  color: #6c7e8d;

  font-size: .78rem;
  line-height: 1.5;
}

.gp2-action-card > strong {
  margin-bottom: .25rem;

  color: #071827;

  font-size: .9rem;
}

.gp2-action-card > a {
  margin-top: auto;
  padding-top: .85rem;

  color: #087f73;

  text-decoration: none;

  font-size: .76rem;
  font-weight: 850;
}

.gp2-site-intro {
  padding: .9rem 1rem 0;

  color: #718492;

  font-size: .76rem;
}

@media (max-width: 760px) {
  .gp2-projects,
  .gp2-project-overview {
    width: calc(100% - 1.2rem);
    padding-top: 2rem;
  }

  .gp2-page-header,
  .gp2-project-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .gp2-project-card {
    grid-template-columns: auto 1fr;
  }

  .gp2-primary-link {
    grid-column: 1 / -1;
  }

  .gp2-action-grid {
    grid-template-columns: 1fr;
  }

  .gp2-command {
    width: 100%;
  }
}
"""

        css_file.write_text(
            css,
            encoding="utf-8",
            newline="\n",
        )

    logline("UI_PATCH = APPLIED")

    # ---------------------------------------------------------
    # TEST
    # ---------------------------------------------------------

    logline("")
    logline("=== FRONTEND TEST ===")

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

    logline(f"TEST_EXIT_CODE = {test_exit}")

    if test_exit != 0:
        raise RuntimeError(
            f"Frontend tests failed: {test_exit}"
        )

    # ---------------------------------------------------------
    # BUILD
    # ---------------------------------------------------------

    logline("")
    logline("=== FRONTEND BUILD ===")

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

    logline(f"BUILD_EXIT_CODE = {build_exit}")

    if build_exit != 0:
        raise RuntimeError(
            f"Frontend build failed: {build_exit}"
        )

    logline("")
    logline("POST_LOGIN_MINIMAL_UI_V2 = PASS")
    logline("BACKEND_WRITE = NONE")
    logline("DATABASE_WRITE = NONE")
    logline("CREATE_SITE_FUNCTION = PRESERVED")

    success = True

except Exception as exc:
    logline("")
    logline("POST_LOGIN_MINIMAL_UI_V2 = ERROR")
    logline(f"ERROR = {exc}")

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

        logline("AUTO_RESTORE = COMPLETE")

    logline("")
    logline("LOG_CAPTURE = COMPLETE")
    logline(f"LOG_FILE = {log}")

print("")
print("RESULT SAVED TO:")
print(log)

sys.exit(0 if success else 1)
