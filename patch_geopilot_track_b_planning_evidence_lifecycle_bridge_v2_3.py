
from pathlib import Path
import re

ROOT = Path("/app/app/services")
gis = ROOT / "gis_analysis.py"
applic = ROOT / "site_applicability.py"
tools = ROOT / "planning_tools.py"
orch = ROOT / "planning_orchestrator.py"

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}_COUNT_{count}")
    return text.replace(old, new, 1)

def regex_once(text: str, pattern: str, repl: str, label: str, flags=0) -> str:
    new, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"{label}_COUNT_{count}")
    return new

# ------------------------------------------------------------
# gis_analysis.py
# ------------------------------------------------------------
t = gis.read_text(encoding="utf-8-sig")

t = replace_once(
    t,
    "from app.services.isolation import SiteScope, resolve_analysis_scope",
    "from app.services.isolation import SiteScope, SiteState, resolve_analysis_scope",
    "GIS_IMPORT",
)

t = replace_once(
    t,
    """def _analysis_scope(
    session: Session, *, owner: User, project_id: uuid.UUID, site_id: uuid.UUID
) -> SiteScope:
    return resolve_analysis_scope(
        session, owner=owner, project_id=project_id, site_id=site_id
    )
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
    "GIS_SCOPE",
)

t = replace_once(
    t,
    """def calculate_site_area(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> SiteAreaResult:
    scope = _analysis_scope(
        session, owner=owner, project_id=project_id, site_id=site_id
    )
    row = _mapping_one(
        session,
        \"\"\"
        SELECT ST_Area(geography(s.geometry)) AS area_sqm
        FROM sites AS s
        WHERE s.id = :site_id
          AND s.project_id = :project_id
          AND s.is_active IS TRUE
          AND s.is_archived IS FALSE
        \"\"\",
        {"site_id": site_id, "project_id": project_id},
    )
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
        f\"\"\"
        SELECT ST_Area(geography(s.geometry)) AS area_sqm
        FROM sites AS s
        WHERE s.id = :site_id
          AND s.project_id = :project_id
          {active_clause}
          AND s.is_archived IS FALSE
        \"\"\",
        {"site_id": site_id, "project_id": project_id},
    )
""",
    "GIS_SITE_AREA",
)

gis.write_text(t, encoding="utf-8")

# ------------------------------------------------------------
# site_applicability.py
# ------------------------------------------------------------
t = applic.read_text(encoding="utf-8-sig")

t = replace_once(
    t,
    "from app.services.isolation import resolve_analysis_scope",
    "from app.services.isolation import SiteState, resolve_analysis_scope",
    "APPLIC_IMPORT",
)

t = replace_once(
    t,
    """def resolve_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> tuple[list[SiteApplicabilityMatch], list[str]]:
""",
    """def resolve_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> tuple[list[SiteApplicabilityMatch], list[str]]:
""",
    "APPLIC_SIGNATURE",
)

t = replace_once(
    t,
    """    scope = resolve_analysis_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
    )
""",
    """    scope = resolve_analysis_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )
""",
    "APPLIC_SCOPE",
)

applic.write_text(t, encoding="utf-8")

# ------------------------------------------------------------
# planning_tools.py
# ------------------------------------------------------------
t = tools.read_text(encoding="utf-8-sig")

if "from app.services.isolation import SiteState" not in t:
    t = replace_once(
        t,
        "from app.models.user import User",
        "from app.models.user import User\nfrom app.services.isolation import SiteState",
        "TOOLS_IMPORT",
    )

t = replace_once(
    t,
    """def execute_site_area(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> ToolEvidence:
""",
    """def execute_site_area(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> ToolEvidence:
""",
    "TOOLS_AREA_SIGNATURE",
)

area_start = t.index("def execute_site_area(")
area_end = t.index("def execute_site_applicability(", area_start)
area_block = t[area_start:area_end]
area_block = replace_once(
    area_block,
    """        project_id=project_id,
        site_id=site_id,
    )
""",
    """        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )
""",
    "TOOLS_AREA_CALL",
)
t = t[:area_start] + area_block + t[area_end:]

t = replace_once(
    t,
    """def execute_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> tuple[list[ToolEvidence], list[str]]:
""",
    """def execute_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> tuple[list[ToolEvidence], list[str]]:
""",
    "TOOLS_APPLIC_SIGNATURE",
)

app_start = t.index("def execute_site_applicability(")
app_end = t.index("def execute_site_terrain_summary(", app_start)
app_block = t[app_start:app_end]
app_block = replace_once(
    app_block,
    """            project_id=project_id,
            site_id=site_id,
        )
""",
    """            project_id=project_id,
            site_id=site_id,
            site_state=site_state,
        )
""",
    "TOOLS_APPLIC_CALL",
)
t = t[:app_start] + app_block + t[app_end:]

tools.write_text(t, encoding="utf-8")

# ------------------------------------------------------------
# planning_orchestrator.py
# ------------------------------------------------------------
t = orch.read_text(encoding="utf-8-sig")

area_start = t.index('if "gis.site_area" in tools:')
area_end = t.index('if "terrain.site_summary" in tools:', area_start)
area_block = t[area_start:area_end]
area_block = replace_once(
    area_block,
    """                project_id=project_id,
                site_id=site_id,
            )
""",
    """                project_id=project_id,
                site_id=site_id,
                site_state=site_state,
            )
""",
    "ORCH_AREA_CALL",
)
t = t[:area_start] + area_block + t[area_end:]

app_start = t.index('if "gis.site_applicability" in tools:')
app_end = t.index('spatial_terms =', app_start)
app_block = t[app_start:app_end]
app_block = replace_once(
    app_block,
    """            project_id=project_id,
            site_id=site_id,
        )
""",
    """            project_id=project_id,
            site_id=site_id,
            site_state=site_state,
        )
""",
    "ORCH_APPLIC_CALL",
)
t = t[:app_start] + app_block + t[app_end:]

orch.write_text(t, encoding="utf-8")

print("PATCHED gis_analysis.py")
print("PATCHED site_applicability.py")
print("PATCHED planning_tools.py")
print("PATCHED planning_orchestrator.py")
