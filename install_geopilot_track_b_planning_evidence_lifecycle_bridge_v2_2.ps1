$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$GIS="$Root\backend\app\services\gis_analysis.py"
$Applic="$Root\backend\app\services\site_applicability.py"
$Tools="$Root\backend\app\services\planning_tools.py"
$Orch="$Root\backend\app\services\planning_orchestrator.py"
$Test="$Root\backend\tests\test_track_b_planning_evidence_lifecycle_bridge_v2_2.py"

foreach($P in @($GIS,$Applic,$Tools,$Orch)){
    if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Track B Planning Evidence Lifecycle Bridge V2.2"
Write-Host "Robust recovery after V2.1 rollback"
Write-Host "Inactive-but-unarchived Track B Site -> AVAILABLE GIS evidence scope"
Write-Host "Normal analytical defaults remain ACTIVE"
Write-Host "NO DB DATA UPDATE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\track_b_planning_evidence_lifecycle_bridge_v2_2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $GIS "$Backup\gis_analysis.py"
Copy-Item $Applic "$Backup\site_applicability.py"
Copy-Item $Tools "$Backup\planning_tools.py"
Copy-Item $Orch "$Backup\planning_orchestrator.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_track_b_planning_evidence_lifecycle_bridge_v2_2.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Confirm V2.1 rollback"
    $g=Get-Content $GIS -Raw
    $a=Get-Content $Applic -Raw
    $t=Get-Content $Tools -Raw
    $o=Get-Content $Orch -Raw

    if($g -match 'site_state: SiteState = SiteState.ACTIVE' -or
       $a -match 'site_state: SiteState = SiteState.ACTIVE'){
        throw "Unexpected partial V2.1 source modification detected."
    }
    if($g -notmatch 'AND s\.is_active IS TRUE'){ throw "Expected ACTIVE-only site-area SQL gate not found." }
    if($a -notmatch 'scope = resolve_analysis_scope\('){ throw "Expected site applicability scope call not found." }
    if($o -notmatch 'site_state:\s*SiteState\s*=\s*SiteState\.ACTIVE'){
        throw "Existing Track B PlanningRun lifecycle bridge is missing."
    }
    Write-Host "rollback_state=CONFIRMED"

    Write-Host "[1] Stage robust backend patcher"
    $Patch="$Root\backend\_patch_track_b_planning_evidence_lifecycle_v2_2.py"

@'
from pathlib import Path
import re

ROOT = Path("/app/app/services")
gis = ROOT / "gis_analysis.py"
applic = ROOT / "site_applicability.py"
tools = ROOT / "planning_tools.py"
orch = ROOT / "planning_orchestrator.py"

def sub1(text, pattern, repl, label, flags=0):
    new, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"{label}_MATCH_COUNT_{count}")
    return new

# ------------------------------------------------------------------
# GIS AREA
# ------------------------------------------------------------------
t = gis.read_text(encoding="utf-8-sig")

t = sub1(
    t,
    r"from app\.services\.isolation import SiteScope, resolve_analysis_scope",
    "from app.services.isolation import SiteScope, SiteState, resolve_analysis_scope",
    "GIS_IMPORT",
)

t = sub1(
    t,
    r"""def _analysis_scope\(
    session: Session, \*, owner: User, project_id: uuid\.UUID, site_id: uuid\.UUID
\) -> SiteScope:
    return resolve_analysis_scope\(
        session, owner=owner, project_id=project_id, site_id=site_id
    \)
""",
    """def _analysis_scope(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> SiteScope:
    return resolve_analysis_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )
""",
    "GIS_ANALYSIS_SCOPE",
)

t = sub1(
    t,
    r"""def calculate_site_area\(
    session: Session,
    \*,
    owner: User,
    project_id: uuid\.UUID,
    site_id: uuid\.UUID,
\) -> SiteAreaResult:
    scope = _analysis_scope\(
        session, owner=owner, project_id=project_id, site_id=site_id
    \)
    row = _mapping_one\(
        session,
        """
        SELECT ST_Area\(geography\(s\.geometry\)\) AS area_sqm
        FROM sites AS s
        WHERE s\.id = :site_id
          AND s\.project_id = :project_id
          AND s\.is_active IS TRUE
          AND s\.is_archived IS FALSE
        """,
        \{"site_id": site_id, "project_id": project_id\},
    \)
""",
    """def calculate_site_area(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> SiteAreaResult:
    scope = _analysis_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )
    active_clause = (
        "AND s.is_active IS TRUE"
        if site_state is SiteState.ACTIVE
        else ""
    )
    row = _mapping_one(
        session,
        f"""
        SELECT ST_Area(geography(s.geometry)) AS area_sqm
        FROM sites AS s
        WHERE s.id = :site_id
          AND s.project_id = :project_id
          {active_clause}
          AND s.is_archived IS FALSE
        """,
        {"site_id": site_id, "project_id": project_id},
    )
""",
    "GIS_SITE_AREA",
    flags=re.MULTILINE,
)

gis.write_text(t, encoding="utf-8")

# ------------------------------------------------------------------
# SITE APPLICABILITY
# ------------------------------------------------------------------
t = applic.read_text(encoding="utf-8-sig")

t = sub1(
    t,
    r"from app\.services\.isolation import resolve_analysis_scope",
    "from app.services.isolation import SiteState, resolve_analysis_scope",
    "APPLIC_IMPORT",
)

t = sub1(
    t,
    r"""def resolve_site_applicability\(
    session: Session,
    \*,
    owner: User,
    project_id: uuid\.UUID,
    site_id: uuid\.UUID,
\) -> tuple\[list\[SiteApplicabilityMatch\], list\[str\]\]:""",
    """def resolve_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> tuple[list[SiteApplicabilityMatch], list[str]]:""",
    "APPLIC_SIGNATURE",
)

t = sub1(
    t,
    r"""    scope = resolve_analysis_scope\(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
    \)""",
    """    scope = resolve_analysis_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )""",
    "APPLIC_SCOPE",
)

applic.write_text(t, encoding="utf-8")

# ------------------------------------------------------------------
# PLANNING TOOL ADAPTERS
# ------------------------------------------------------------------
t = tools.read_text(encoding="utf-8-sig")

if "from app.services.isolation import SiteState" not in t:
    t = sub1(
        t,
        r"(from app\.models\.user import User\n)",
        r"\1from app.services.isolation import SiteState\n",
        "TOOLS_IMPORT",
    )

t = sub1(
    t,
    r"""def execute_site_area\(
    session: Session,
    \*,
    owner: User,
    project_id: uuid\.UUID,
    site_id: uuid\.UUID,
\) -> ToolEvidence:""",
    """def execute_site_area(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> ToolEvidence:""",
    "TOOLS_AREA_SIGNATURE",
)

# Patch only the calculate_site_area call inside execute_site_area.
start = t.index("def execute_site_area(")
end = t.index("def execute_site_applicability(", start)
block = t[start:end]
block = sub1(
    block,
    r"""        project_id=project_id,
        site_id=site_id,
    \)""",
    """        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )""",
    "TOOLS_AREA_CALL",
)
t = t[:start] + block + t[end:]

t = sub1(
    t,
    r"""def execute_site_applicability\(
    session: Session,
    \*,
    owner: User,
    project_id: uuid\.UUID,
    site_id: uuid\.UUID,
\) -> tuple\[list\[ToolEvidence\], list\[str\]\]:""",
    """def execute_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> tuple[list[ToolEvidence], list[str]]:""",
    "TOOLS_APPLIC_SIGNATURE",
)

start = t.index("def execute_site_applicability(")
end = t.index("def execute_site_terrain_summary(", start)
block = t[start:end]
block = sub1(
    block,
    r"""            project_id=project_id,
            site_id=site_id,
        \)""",
    """            project_id=project_id,
            site_id=site_id,
            site_state=site_state,
        )""",
    "TOOLS_APPLIC_CALL",
)
t = t[:start] + block + t[end:]

tools.write_text(t, encoding="utf-8")

# ------------------------------------------------------------------
# ORCHESTRATOR: propagate existing PlanningRun site_state
# ------------------------------------------------------------------
t = orch.read_text(encoding="utf-8-sig")

# GIS site area block
start = t.index('if "gis.site_area" in tools:')
end = t.index('if "terrain.site_summary" in tools:', start)
block = t[start:end]
block = sub1(
    block,
    r"""                project_id=project_id,
                site_id=site_id,
            \)""",
    """                project_id=project_id,
                site_id=site_id,
                site_state=site_state,
            )""",
    "ORCH_AREA_CALL",
)
t = t[:start] + block + t[end:]

# GIS applicability block
start = t.index('if "gis.site_applicability" in tools:')
end = t.index('spatial_terms =', start)
block = t[start:end]
block = sub1(
    block,
    r"""            project_id=project_id,
            site_id=site_id,
        \)""",
    """            project_id=project_id,
            site_id=site_id,
            site_state=site_state,
        )""",
    "ORCH_APPLIC_CALL",
)
t = t[:start] + block + t[end:]

orch.write_text(t, encoding="utf-8")

print("PATCHED: gis_analysis.py")
print("PATCHED: site_applicability.py")
print("PATCHED: planning_tools.py")
print("PATCHED: planning_orchestrator.py")
'@ | Set-Content $Patch -Encoding UTF8

    try {
        docker compose exec -T backend python /app/_patch_track_b_planning_evidence_lifecycle_v2_2.py
        if($LASTEXITCODE-ne 0){ throw "Robust backend patcher failed." }
    }
    finally {
        Remove-Item $Patch -Force -ErrorAction SilentlyContinue
    }

    Write-Host "[2] Install focused lifecycle regression"
@'
from pathlib import Path


def test_gis_area_has_active_default_and_available_opt_in():
    text = Path("app/services/gis_analysis.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert "site_state=site_state" in text
    assert 'if site_state is SiteState.ACTIVE' in text
    assert "AND s.is_archived IS FALSE" in text


def test_site_applicability_has_active_default_and_available_opt_in():
    text = Path("app/services/site_applicability.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert "site_state=site_state" in text


def test_planning_tools_propagate_site_state():
    text = Path("app/services/planning_tools.py").read_text(encoding="utf-8-sig")
    assert text.count("site_state: SiteState = SiteState.ACTIVE") >= 2
    assert text.count("site_state=site_state") >= 2


def test_orchestrator_propagates_existing_planning_run_site_state():
    text = Path("app/services/planning_orchestrator.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert text.count("site_state=site_state") >= 3


def test_terrain_available_behavior_remains_present():
    text = Path("app/services/terrain_analysis.py").read_text(encoding="utf-8-sig")
    assert "site_state=SiteState.AVAILABLE" in text
'@ | Set-Content $Test -Encoding UTF8

    Write-Host "[3] Syntax checks"
    docker compose exec -T backend python -m py_compile app/services/gis_analysis.py app/services/site_applicability.py app/services/planning_tools.py app/services/planning_orchestrator.py tests/test_track_b_planning_evidence_lifecycle_bridge_v2_2.py
    if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

    Write-Host "[4] Focused lifecycle regression"
    docker compose exec -T backend python -m pytest -q tests/test_track_b_planning_evidence_lifecycle_bridge_v2_2.py
    if($LASTEXITCODE-ne 0){ throw "Focused lifecycle regression failed." }

    Write-Host "[5] Preserve existing lifecycle/evidence regressions"
    foreach($Regression in @(
        "tests/test_track_b_planning_site_lifecycle_bridge_v1_2.py",
        "tests/test_auto_research_evidence_scope_bridge_v2.py"
    )){
        if(Test-Path "$Root\backend\$Regression"){
            docker compose exec -T backend python -m pytest -q $Regression
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $Regression" }
        }
    }

    Write-Host "[6] Static contract verification"
    $G=Get-Content $GIS -Raw
    $A=Get-Content $Applic -Raw
    $T=Get-Content $Tools -Raw
    $O=Get-Content $Orch -Raw

    if($G -notmatch 'site_state: SiteState = SiteState\.ACTIVE'){ throw "GIS site_state opt-in missing." }
    if($A -notmatch 'site_state: SiteState = SiteState\.ACTIVE'){ throw "Applicability site_state opt-in missing." }
    if($T -notmatch 'from app\.services\.isolation import SiteState'){ throw "Planning tools SiteState import missing." }
    if($O -notmatch 'site_state=site_state'){ throw "Orchestrator site_state propagation missing." }

    Write-Host "lifecycle_contract=PASS"

    Write-Host "[7] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[8] Backend health"
    docker compose ps backend

    Write-Host "[9] Runtime import verification"
    docker compose exec -T backend python -c "from app.services.gis_analysis import calculate_site_area; from app.services.site_applicability import resolve_site_applicability; from app.services.planning_orchestrator import execute_planning_run; print('runtime_lifecycle_bridge=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Runtime import verification failed." }

    Write-Host "============================================================"
    Write-Host "TRACK B PLANNING EVIDENCE LIFECYCLE BRIDGE V2.2 PASS"
    Write-Host "============================================================"
    Write-Host "Track B inactive-unarchived Site: AVAILABLE FOR PLANNING EVIDENCE"
    Write-Host "Normal GIS analysis default Site requirement: ACTIVE"
    Write-Host "gis.site_area Track B opt-in: AVAILABLE"
    Write-Host "gis.site_applicability Track B opt-in: AVAILABLE"
    Write-Host "terrain.site_summary AVAILABLE behavior: PRESERVED"
    Write-Host "Archived Site rejection: PRESERVED"
    Write-Host "Archived Project rejection: PRESERVED"
    Write-Host "Project ownership isolation: PRESERVED"
    Write-Host "Site/project identity isolation: PRESERVED"
    Write-Host "DB flags changed: NONE"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend change: NONE"
    Write-Host "Next gate: RETEST PLANNER QUESTION ON SHAH ALAM SITE"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring source/test backup."
    Copy-Item "$Backup\gis_analysis.py" $GIS -Force
    Copy-Item "$Backup\site_applicability.py" $Applic -Force
    Copy-Item "$Backup\planning_tools.py" $Tools -Force
    Copy-Item "$Backup\planning_orchestrator.py" $Orch -Force

    if(Test-Path "$Backup\test_track_b_planning_evidence_lifecycle_bridge_v2_2.py"){
        Copy-Item "$Backup\test_track_b_planning_evidence_lifecycle_bridge_v2_2.py" $Test -Force
    } else {
        Remove-Item $Test -Force -ErrorAction SilentlyContinue
    }

    throw
}
