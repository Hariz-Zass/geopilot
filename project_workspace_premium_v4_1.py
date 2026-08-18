from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path.cwd()

tsx = ROOT / "frontend/src/pages/ProjectPage.tsx"
css = ROOT / "frontend/src/styles.css"
artifacts = ROOT / "artifacts"

artifacts.mkdir(exist_ok=True)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

tsx_backup = artifacts / f"ProjectPage.pre_premium_v4_1_{stamp}.tsx"
css_backup = artifacts / f"styles.pre_premium_v4_1_{stamp}.css"
log = artifacts / "project_workspace_premium_v4_1.txt"

shutil.copy2(tsx, tsx_backup)
shutil.copy2(css, css_backup)

source = tsx.read_text(encoding="utf-8-sig")
styles = css.read_text(encoding="utf-8-sig")

old_hero = '''      <header className="gp2-project-hero">
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
'''

new_hero = '''      <header className="gp2-project-hero gp-premium-project-hero">
        <div className="gp-premium-project-copy">
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
'''

if old_hero not in source:
    raise RuntimeError(
        "Expected ProjectPage hero block not found. "
        "No source file was changed."
    )

source = source.replace(old_hero, new_hero, 1)

tsx.write_text(
    source,
    encoding="utf-8",
    newline="\n",
)

marker = "/* GEOPILOT PROJECT WORKSPACE PREMIUM V4.1 */"

if marker not in styles:
    styles += r'''

/* ============================================================
   GEOPILOT PROJECT WORKSPACE PREMIUM V4.1
   FULL-BLEED PREMIUM COMPOSITION
   ============================================================ */

/* ---------- REMOVE GREY / WHITE OUTER CANVAS ---------- */

html:has(.gp2-project-overview),
body:has(.gp2-project-overview),
body:has(.gp2-project-overview) #root,
body:has(.gp2-project-overview) .app-shell,
body:has(.gp2-project-overview) main,
body:has(.gp2-project-overview) .app-content {
  background: #06131f !important;
}

body:has(.gp2-project-overview) main,
body:has(.gp2-project-overview) .app-content {
  width: 100% !important;
  max-width: none !important;
  margin: 0 !important;
  padding: 0 !important;
}

/* ---------- PREMIUM FULL PAGE BACKGROUND ---------- */

body:has(.gp2-project-overview) .app-content {
  min-height: calc(100vh - 72px);

  background:
    radial-gradient(
      circle at 12% 18%,
      rgba(23, 196, 177, .12),
      transparent 27%
    ),
    radial-gradient(
      circle at 86% 11%,
      rgba(32, 91, 151, .19),
      transparent 31%
    ),
    radial-gradient(
      circle at 74% 78%,
      rgba(14, 112, 116, .09),
      transparent 31%
    ),
    linear-gradient(
      135deg,
      #04121c 0%,
      #071b29 48%,
      #071525 100%
    ) !important;

  position: relative;
  overflow-x: hidden;
}

body:has(.gp2-project-overview) .app-content::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;

  background-image:
    linear-gradient(
      rgba(75, 221, 204, .025) 1px,
      transparent 1px
    ),
    linear-gradient(
      90deg,
      rgba(75, 221, 204, .025) 1px,
      transparent 1px
    );

  background-size: 52px 52px;
  opacity: .8;
}

/* ---------- CONTENT CANVAS ---------- */

.gp2-project-overview {
  width: min(1280px, calc(100% - 5rem)) !important;
  min-height: calc(100vh - 72px);

  margin: 0 auto !important;
  padding: 4rem 0 5rem !important;

  position: relative;
  z-index: 2;
}

/* ---------- HERO ---------- */

.gp-premium-project-hero {
  display: grid !important;
  grid-template-columns:
    minmax(0, 1.55fr)
    minmax(290px, .65fr) !important;

  align-items: stretch !important;
  gap: 2.4rem !important;

  margin-bottom: 1.35rem !important;
}

.gp-premium-project-copy {
  min-height: 315px;

  display: flex;
  flex-direction: column;
  justify-content: center;

  padding: .5rem 0;
}

.gp-premium-project-copy .eyebrow {
  margin-bottom: .85rem !important;

  color: #5fe2d2 !important;

  font-size: .62rem !important;
  font-weight: 900 !important;

  letter-spacing: .22em !important;
}

/* ---------- TITLE SIZE / WEIGHT ---------- */

.gp-premium-project-copy h1 {
  max-width: 850px !important;

  margin: 0 0 1rem !important;

  color: #f0f6f7 !important;

  font-size: clamp(
    2.8rem,
    4vw,
    3.75rem
  ) !important;

  line-height: 1.01 !important;

  letter-spacing: -.044em !important;

  font-weight: 760 !important;

  text-wrap: balance;
}

/* ---------- DESCRIPTION ---------- */

.gp-premium-project-copy
.gp2-project-description {
  max-width: 820px !important;

  margin: 0 !important;

  color: #91a9b6 !important;

  font-size: .91rem !important;

  line-height: 1.72 !important;
}

/* ---------- HERO META ---------- */

.gp-premium-project-meta {
  display: flex;
  flex-wrap: wrap;

  gap: .45rem;

  margin-top: 1.35rem;
}

.gp-premium-project-meta span {
  padding: .28rem .48rem;

  border: 1px solid
    rgba(95, 226, 210, .15);

  border-radius: 5px;

  background:
    rgba(24, 80, 83, .12);

  color: #78b9b5;

  font-size: .53rem;
  font-weight: 850;

  letter-spacing: .085em;
}

/* ---------- PROJECT STATUS PANEL ---------- */

.gp-premium-status-panel {
  min-height: 315px;

  padding: 1.35rem;

  display: flex;
  flex-direction: column;

  border:
    1px solid rgba(95, 226, 210, .17);

  border-radius: 15px;

  background:
    radial-gradient(
      circle at 100% 0%,
      rgba(66, 210, 193, .07),
      transparent 37%
    ),
    linear-gradient(
      145deg,
      rgba(11, 36, 51, .94),
      rgba(7, 25, 38, .94)
    );

  box-shadow:
    inset 0 1px
      rgba(255,255,255,.026),
    0 25px 60px
      rgba(0,0,0,.13);

  backdrop-filter: blur(16px);
}

.gp-premium-status-heading {
  display: flex;
  align-items: center;

  gap: .5rem;

  padding-bottom: 1rem;

  border-bottom:
    1px solid rgba(109, 169, 184, .10);

  color: #64dace;

  font-size: .59rem;
  font-weight: 900;

  letter-spacing: .13em;
}

.gp-premium-status-dot {
  width: 7px;
  height: 7px;

  border-radius: 50%;

  background: #60ddcf;

  box-shadow:
    0 0 12px
    rgba(96, 221, 207, .5);
}

.gp-premium-status-main {
  padding: 1.3rem 0;

  display: grid;
  gap: .27rem;
}

.gp-premium-status-main strong {
  color: #e8f3f4;

  font-size: 1.05rem;
  font-weight: 800;
}

.gp-premium-status-main span {
  color: #7291a1;

  font-size: .72rem;
}

.gp-premium-status-grid {
  display: grid;
  grid-template-columns:
    repeat(2, 1fr);

  gap: .6rem;

  margin-bottom: 1rem;
}

.gp-premium-status-grid > div {
  padding: .65rem .72rem;

  border:
    1px solid rgba(113, 169, 184, .105);

  border-radius: 8px;

  background:
    rgba(4, 21, 32, .42);
}

.gp-premium-status-grid small,
.gp-premium-status-grid strong {
  display: block;
}

.gp-premium-status-grid small {
  margin-bottom: .18rem;

  color: #668191;

  font-size: .49rem;

  font-weight: 850;

  letter-spacing: .09em;
}

.gp-premium-status-grid strong {
  color: #91d5cf;

  font-size: .65rem;

  font-weight: 900;
}

/* ---------- COMMAND CENTER CTA ---------- */

.gp-premium-command {
  width: 100% !important;
  min-width: 0 !important;

  min-height: 52px !important;

  margin-top: auto;

  padding: 0 .95rem !important;

  border:
    1px solid rgba(91, 223, 209, .38) !important;

  background:
    linear-gradient(
      110deg,
      rgba(19, 76, 86, .82),
      rgba(10, 43, 59, .96)
    ) !important;

  color: #eafafa !important;

  box-shadow:
    inset 0 1px
      rgba(255,255,255,.035),
    0 12px 30px
      rgba(0,0,0,.16) !important;
}

.gp-premium-command:hover {
  border-color:
    rgba(103, 235, 221, .70) !important;

  background:
    linear-gradient(
      110deg,
      rgba(24, 98, 103, .86),
      rgba(11, 51, 69, .98)
    ) !important;
}

/* ---------- MODULE CARDS ---------- */

.gp2-action-grid {
  gap: 1rem !important;
}

.gp2-action-card {
  min-height: 230px !important;

  padding: 1.35rem !important;

  border:
    1px solid rgba(105, 164, 180, .14) !important;

  border-radius: 14px !important;

  background:
    radial-gradient(
      circle at 95% 6%,
      rgba(67, 211, 194, .045),
      transparent 36%
    ),
    linear-gradient(
      145deg,
      rgba(10, 34, 49, .93),
      rgba(7, 25, 38, .94)
    ) !important;
}

.gp2-action-card h2 {
  color: #e8f2f3 !important;

  font-size: 1.14rem !important;

  font-weight: 780 !important;
}

.gp2-action-card p {
  color: #8199a7 !important;

  font-size: .77rem !important;
}

/* ---------- ADVANCED SETUP BAR ---------- */

.gp2-details {
  border-color:
    rgba(101, 163, 179, .13) !important;

  background:
    rgba(7, 25, 38, .84) !important;
}

/* ---------- REMOVE OLD CENTER-PANEL FEEL ---------- */

.gp2-project-overview::after {
  content: none !important;
}

/* ---------- RESPONSIVE ---------- */

@media (max-width: 1050px) {

  .gp-premium-project-hero {
    grid-template-columns: 1fr !important;
  }

  .gp-premium-project-copy {
    min-height: auto;
  }

  .gp-premium-status-panel {
    min-height: auto;
  }
}

@media (max-width: 760px) {

  .gp2-project-overview {
    width:
      calc(100% - 1.4rem) !important;

    padding:
      2.4rem 0 4rem !important;
  }

  .gp-premium-project-copy h1 {
    font-size:
      clamp(
        2.15rem,
        11vw,
        3rem
      ) !important;
  }

  .gp-premium-project-meta {
    display: none;
  }
}

'''

    css.write_text(
        styles,
        encoding="utf-8",
        newline="\n",
    )

log.write_text(
    "\n".join([
        "============================================================",
        "GEOPILOT PROJECT WORKSPACE PREMIUM V4.1",
        "============================================================",
        f"TSX_BACKUP = {tsx_backup}",
        f"CSS_BACKUP = {css_backup}",
        "HERO_COMPOSITION = UPDATED",
        "FULL_BLEED_BACKGROUND = INSTALLED",
        "PROJECT_STATUS_PANEL = INSTALLED",
        "FUNCTION_LOGIC_CHANGE = NONE",
        "BACKEND_CHANGE = NONE",
        "DATABASE_CHANGE = NONE",
        "PATCH_STATUS = APPLIED",
    ]) + "\n",
    encoding="utf-8",
)

print("")
print("PROJECT WORKSPACE PREMIUM V4.1 = APPLIED")
print("LOG:")
print(log)
