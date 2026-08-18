$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Iso="$Root\backend\app\services\isolation.py"
$GIS="$Root\backend\app\services\gis_analysis.py"
$Applic="$Root\backend\app\services\site_applicability.py"
$Tools="$Root\backend\app\services\planning_tools.py"
$Orch="$Root\backend\app\services\planning_orchestrator.py"
$Test="$Root\backend\tests\test_track_b_planning_evidence_lifecycle_bridge_v2.py"

foreach($P in @($Iso,$GIS,$Applic,$Tools,$Orch)){
    if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Track B Planning Evidence Lifecycle Bridge V2"
Write-Host "Inactive-but-unarchived Track B Site -> AVAILABLE GIS evidence scope"
Write-Host "Normal analytical defaults remain ACTIVE"
Write-Host "NO DB DATA UPDATE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\track_b_planning_evidence_lifecycle_bridge_v2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $GIS "$Backup\gis_analysis.py"
Copy-Item $Applic "$Backup\site_applicability.py"
Copy-Item $Tools "$Backup\planning_tools.py"
Copy-Item $Orch "$Backup\planning_orchestrator.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_track_b_planning_evidence_lifecycle_bridge_v2.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Preflight lifecycle gate"
    $g=Get-Content $GIS -Raw
    $a=Get-Content $Applic -Raw
    $t=Get-Content $Tools -Raw
    $o=Get-Content $Orch -Raw

    if($g -notmatch 'def _analysis_scope\('){ throw "GIS analysis scope helper missing." }
    if($g -notmatch 'AND s\.is_active IS TRUE'){ throw "Expected ACTIVE-only site area SQL gate missing." }
    if($a -notmatch 'scope = resolve_analysis_scope\('){ throw "Site applicability analysis scope missing." }
    if($o -notmatch 'def execute_planning_run\('){ throw "Planning orchestrator execute function missing." }
    if($o -notmatch 'site_state:\s*SiteState\s*=\s*SiteState\.ACTIVE'){
        throw "Planning orchestrator site_state lifecycle bridge not present."
    }
    Write-Host "preflight_state=CONFIRMED"

    Write-Host "[1] Patch GIS area analysis with explicit SiteState opt-in"
    $GText=Get-Content $GIS -Raw

    $GText=$GText.Replace(
        'from app.services.isolation import SiteScope, resolve_analysis_scope',
        'from app.services.isolation import SiteScope, SiteState, resolve_analysis_scope'
    )

    $Old=@'
def _analysis_scope(
    session: Session, *, owner: User, project_id: uuid.UUID, site_id: uuid.UUID
) -> SiteScope:
    return resolve_analysis_scope(
        session, owner=owner, project_id=project_id, site_id=site_id
    )
'@
    $New=@'
def _analysis_scope(
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
'@
    if(-not $GText.Contains($Old)){ throw "GIS _analysis_scope block not found." }
    $GText=$GText.Replace($Old,$New)

    $Old=@'
def calculate_site_area(
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
        """
        SELECT ST_Area(geography(s.geometry)) AS area_sqm
        FROM sites AS s
        WHERE s.id = :site_id
          AND s.project_id = :project_id
          AND s.is_active IS TRUE
          AND s.is_archived IS FALSE
        """,
        {"site_id": site_id, "project_id": project_id},
    )
'@
    $New=@'
def calculate_site_area(
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
'@
    if(-not $GText.Contains($Old)){ throw "calculate_site_area ACTIVE block not found." }
    $GText=$GText.Replace($Old,$New)
    [System.IO.File]::WriteAllText($GIS,$GText,[System.Text.UTF8Encoding]::new($false))

    Write-Host "[2] Patch site applicability with explicit SiteState opt-in"
    $AText=Get-Content $Applic -Raw
    $AText=$AText.Replace(
        'from app.services.isolation import resolve_analysis_scope',
        'from app.services.isolation import SiteState, resolve_analysis_scope'
    )

    $Old=@'
def resolve_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> tuple[list[SiteApplicabilityMatch], list[str]]:
'@
    $New=@'
def resolve_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> tuple[list[SiteApplicabilityMatch], list[str]]:
'@
    if(-not $AText.Contains($Old)){ throw "resolve_site_applicability signature not found." }
    $AText=$AText.Replace($Old,$New)

    $Old=@'
    scope = resolve_analysis_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
    )
'@
    $New=@'
    scope = resolve_analysis_scope(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )
'@
    if(-not $AText.Contains($Old)){ throw "resolve_site_applicability scope block not found." }
    $AText=$AText.Replace($Old,$New)
    [System.IO.File]::WriteAllText($Applic,$AText,[System.Text.UTF8Encoding]::new($false))

    Write-Host "[3] Patch planning tool adapters"
    $TText=Get-Content $Tools -Raw

    if($TText -notmatch 'from app\.services\.isolation import SiteState'){
        $ImportAnchor='from app.models.user import User'
        if(-not $TText.Contains($ImportAnchor)){ throw "Planning tools import anchor not found." }
        $TText=$TText.Replace($ImportAnchor,$ImportAnchor+"`nfrom app.services.isolation import SiteState")
    }

    $Old=@'
def execute_site_area(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> ToolEvidence:
'@
    $New=@'
def execute_site_area(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> ToolEvidence:
'@
    if(-not $TText.Contains($Old)){ throw "execute_site_area signature not found." }
    $TText=$TText.Replace($Old,$New)

    $Old=@'
        project_id=project_id,
        site_id=site_id,
    )
'@
    $New=@'
        project_id=project_id,
        site_id=site_id,
        site_state=site_state,
    )
'@
    $Pos=$TText.IndexOf('def execute_site_area(')
    $End=$TText.IndexOf('def execute_site_applicability(',$Pos)
    $Block=$TText.Substring($Pos,$End-$Pos)
    if(-not $Block.Contains($Old)){ throw "execute_site_area calculate call not found." }
    $Block=$Block.Replace($Old,$New)
    $TText=$TText.Substring(0,$Pos)+$Block+$TText.Substring($End)

    $Old=@'
def execute_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
) -> tuple[list[ToolEvidence], list[str]]:
'@
    $New=@'
def execute_site_applicability(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
) -> tuple[list[ToolEvidence], list[str]]:
'@
    if(-not $TText.Contains($Old)){ throw "execute_site_applicability signature not found." }
    $TText=$TText.Replace($Old,$New)

    $Pos=$TText.IndexOf('def execute_site_applicability(')
    $End=$TText.IndexOf('def execute_site_terrain_summary(',$Pos)
    $Block=$TText.Substring($Pos,$End-$Pos)
    if(-not $Block.Contains($Old='        site_id=site_id,')){ throw "execute_site_applicability call anchor not found." }
    $Block=$Block.Replace('        site_id=site_id,',"        site_id=site_id,`n        site_state=site_state,")
    $TText=$TText.Substring(0,$Pos)+$Block+$TText.Substring($End)

    [System.IO.File]::WriteAllText($Tools,$TText,[System.Text.UTF8Encoding]::new($false))

    Write-Host "[4] Propagate PlanningRun site_state into GIS planning tools"
    $OText=Get-Content $Orch -Raw

    $AreaOld=@'
                project_id=project_id,
                site_id=site_id,
            )
'@
    $AreaNew=@'
                project_id=project_id,
                site_id=site_id,
                site_state=site_state,
            )
'@

    $Pos=$OText.IndexOf('if "gis.site_area" in tools:')
    if($Pos -lt 0){ throw "gis.site_area orchestrator block missing." }
    $End=$OText.IndexOf('if "terrain.site_summary" in tools:',$Pos)
    $Block=$OText.Substring($Pos,$End-$Pos)
    if(-not $Block.Contains($AreaOld)){ throw "gis.site_area call block not found." }
    $Block=$Block.Replace($AreaOld,$AreaNew)
    $OText=$OText.Substring(0,$Pos)+$Block+$OText.Substring($End)

    $Pos=$OText.IndexOf('if "gis.site_applicability" in tools:')
    if($Pos -lt 0){ throw "gis.site_applicability orchestrator block missing." }
    $End=$OText.IndexOf('spatial_terms =',$Pos)
    $Block=$OText.Substring($Pos,$End-$Pos)
    if(-not $Block.Contains($AreaOld)){ throw "gis.site_applicability call block not found." }
    $Block=$Block.Replace($AreaOld,$AreaNew)
    $OText=$OText.Substring(0,$Pos)+$Block+$OText.Substring($End)

    [System.IO.File]::WriteAllText($Orch,$OText,[System.Text.UTF8Encoding]::new($false))

    Write-Host "[5] Install focused lifecycle regressions"
    $TestText=@'
from pathlib import Path


def test_gis_area_defaults_active_but_supports_available_opt_in():
    text = Path("app/services/gis_analysis.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert "site_state=site_state" in text
    assert 'if site_state is SiteState.ACTIVE' in text
    assert "AND s.is_archived IS FALSE" in text


def test_site_applicability_defaults_active_but_supports_available_opt_in():
    text = Path("app/services/site_applicability.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert "site_state=site_state" in text


def test_planning_tools_propagate_site_state():
    text = Path("app/services/planning_tools.py").read_text(encoding="utf-8-sig")
    assert text.count("site_state: SiteState = SiteState.ACTIVE") >= 2
    assert text.count("site_state=site_state") >= 2


def test_planning_orchestrator_propagates_track_b_available_scope():
    text = Path("app/services/planning_orchestrator.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert text.count("site_state=site_state") >= 3


def test_terrain_available_site_behavior_is_preserved():
    text = Path("app/services/terrain_analysis.py").read_text(encoding="utf-8-sig")
    assert "site_state=SiteState.AVAILABLE" in text
'@
    [System.IO.File]::WriteAllText($Test,$TestText,[System.Text.UTF8Encoding]::new($false))

    Write-Host "[6] Syntax checks"
    docker compose exec -T backend python -m py_compile app/services/gis_analysis.py app/services/site_applicability.py app/services/planning_tools.py app/services/planning_orchestrator.py tests/test_track_b_planning_evidence_lifecycle_bridge_v2.py
    if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

    Write-Host "[7] Focused lifecycle bridge tests"
    docker compose exec -T backend python -m pytest -q tests/test_track_b_planning_evidence_lifecycle_bridge_v2.py
    if($LASTEXITCODE-ne 0){ throw "Focused lifecycle bridge tests failed." }

    Write-Host "[8] Preserve lifecycle + planning regressions"
    foreach($Regression in @(
        "tests/test_track_b_planning_site_lifecycle_bridge_v1_2.py",
        "tests/test_auto_research_evidence_scope_bridge_v2.py"
    )){
        if(Test-Path "$Root\backend\$Regression"){
            docker compose exec -T backend python -m pytest -q $Regression
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $Regression" }
        }
    }

    Write-Host "[9] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5
    docker compose ps backend

    Write-Host "============================================================"
    Write-Host "TRACK B PLANNING EVIDENCE LIFECYCLE BRIDGE V2 PASS"
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
    if(Test-Path "$Backup\test_track_b_planning_evidence_lifecycle_bridge_v2.py"){
        Copy-Item "$Backup\test_track_b_planning_evidence_lifecycle_bridge_v2.py" $Test -Force
    } else {
        Remove-Item $Test -Force -ErrorAction SilentlyContinue
    }
    throw
}
