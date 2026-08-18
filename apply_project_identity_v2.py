from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path.cwd()
tsx = ROOT / "frontend/src/pages/ProjectPage.tsx"
css = ROOT / "frontend/src/styles.css"
artifacts = ROOT / "artifacts"

artifacts.mkdir(exist_ok=True)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
tsx_backup = artifacts / f"ProjectPage.pre_project_identity_v2_{stamp}.tsx"
css_backup = artifacts / f"styles.pre_project_identity_v2_{stamp}.css"

shutil.copy2(tsx, tsx_backup)
shutil.copy2(css, css_backup)

source = tsx.read_text(encoding="utf-8-sig")
styles = css.read_text(encoding="utf-8-sig")

old = '''          <div className="gp-final-project-identity">
            <span className="gp-final-project-identity-label">
              ACTIVE PROJECT
            </span>
            <strong>
              {loading
                ? "Loading project..."
                : (project?.name ?? "Planning Project")
                    .replace(/\\s*Acceptance Test\\s*/gi, "")
                    .trim()}
            </strong>
          </div>

          {project?.description && (
            <p className="gp2-project-description">
              {project.description}
            </p>
          )}'''

new = '''          <div className="gp-final-project-identity">
            <span className="gp-final-project-identity-label">
              ACTIVE PROJECT
            </span>

            <strong className="gp-final-project-name">
              {loading
                ? "Loading project..."
                : (project?.name ?? "Planning Project")
                    .replace(/\\s*Acceptance Test\\s*/gi, "")
                    .trim()}
            </strong>
          </div>

          <p className="gp2-project-description">
            AI-powered geospatial planning workspace integrating
            spatial analysis, satellite intelligence, planning policy,
            and evidence-grounded decision support.
          </p>'''

if old not in source:
    raise RuntimeError(
        "Expected project identity block not found. No file changed."
    )

source = source.replace(old, new, 1)

tsx.write_text(
    source,
    encoding="utf-8",
    newline="\n",
)

marker = "/* GEOPILOT PROJECT IDENTITY V2 */"

if marker not in styles:
    styles += r'''

/* ============================================================
   GEOPILOT PROJECT IDENTITY V2
   ============================================================ */

.gp-final-project-identity {
  display: grid;
  gap: .42rem;

  margin:
    .2rem 0
    1.15rem;
}

.gp-final-project-identity-label {
  width: fit-content;

  padding:
    .28rem
    .46rem;

  border:
    1px solid
    rgba(95, 226, 210, .24);

  border-radius:
    5px;

  background:
    rgba(24, 92, 91, .14);

  color:
    #69ddd1;

  font-size:
    .49rem;

  font-weight:
    900;

  letter-spacing:
    .13em;
}

.gp-final-project-name {
  color:
    #d9e9ec;

  font-size:
    clamp(
      .95rem,
      1.3vw,
      1.15rem
    );

  font-weight:
    760;

  letter-spacing:
    -.01em;

  line-height:
    1.25;
}

/* improve project description readability */

.gp-premium-project-copy
.gp2-project-description {
  max-width:
    790px !important;

  color:
    #91a9b6 !important;

  font-size:
    .88rem !important;

  line-height:
    1.68 !important;
}

'''

    css.write_text(
        styles,
        encoding="utf-8",
        newline="\n",
    )

print("PROJECT IDENTITY V2 = APPLIED")
print(f"TSX BACKUP = {tsx_backup}")
print(f"CSS BACKUP = {css_backup}")
print("DATABASE CHANGE = NONE")
print("BACKEND CHANGE = NONE")
