from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path.cwd()
path = ROOT / "frontend/src/pages/ProjectPage.tsx"
artifacts = ROOT / "artifacts"

artifacts.mkdir(exist_ok=True)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = artifacts / f"ProjectPage.pre_final_workspace_identity_{stamp}.tsx"

shutil.copy2(path, backup)

content = path.read_text(encoding="utf-8-sig")

old = '''          <h1>
            {loading
              ? "Loading project..."
              : project?.name ?? "Project"}
          </h1>

          {project?.description && (
            <p className="gp2-project-description">
              {project.description}
            </p>
          )}'''

new = '''          <h1>
            GeoPilot AI Planning Workspace
          </h1>

          <div className="gp-final-project-identity">
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

if old not in content:
    raise RuntimeError(
        "Expected premium hero title block not found. "
        "NO FILE WAS CHANGED."
    )

content = content.replace(old, new, 1)

path.write_text(
    content,
    encoding="utf-8",
    newline="\n"
)

print("FINAL WORKSPACE IDENTITY = APPLIED")
print(f"BACKUP = {backup}")
print("DATABASE CHANGE = NONE")
print("BACKEND CHANGE = NONE")
print("PROJECT NAME STORED IN DB = UNCHANGED")
