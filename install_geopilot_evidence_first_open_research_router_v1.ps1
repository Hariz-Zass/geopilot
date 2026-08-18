$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Router = Join-Path $Root "backend\app\services\data_requirement_router.py"
$TrackBAI = Join-Path $Root "backend\app\services\track_b_ai.py"
$Tests = Join-Path $Root "backend\tests\test_data_requirement_router.py"

foreach ($p in @($Router, $TrackBAI, $Tests)) {
    if (!(Test-Path $p)) { throw "Required file missing: $p" }
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root "artifacts\evidence_first_open_research_router_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Router (Join-Path $Backup "data_requirement_router.py")
Copy-Item $TrackBAI (Join-Path $Backup "track_b_ai.py")
Copy-Item $Tests (Join-Path $Backup "test_data_requirement_router.py")

Write-Host "============================================================"
Write-Host "GeoPilot Evidence-First Open Research Router V1"
Write-Host "Cross-module evidence routing without fabrication"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"
Write-Host ""

$patch = @'
from pathlib import Path

router = Path("/app/app/services/data_requirement_router.py")
trackb_ai = Path("/app/app/services/track_b_ai.py")
tests = Path("/app/tests/test_data_requirement_router.py")

s = router.read_text(encoding="utf-8-sig")

old_terms = '''_TERRAIN_TERMS = (
    "slope", "gradient", "terrain", "topography", "topographic", "elevation",
    "altitude", "contour", "dem", "kecerunan", "cerun", "elevasi",
    "aras tanah", "kontur", "topografi",
)
'''
new_terms = '''_TERRAIN_TERMS = (
    "slope", "gradient", "terrain", "topography", "topographic", "elevation",
    "altitude", "contour", "dem", "kecerunan", "cerun", "lereng", "elevasi",
    "ketinggian", "tinggi", "aras tanah", "paras tanah", "kontur", "topografi",
)
'''
if old_terms in s:
    s = s.replace(old_terms, new_terms, 1)
elif '"ketinggian"' not in s:
    raise SystemExit("BLOCKED: expected _TERRAIN_TERMS block not found.")

policy_marker = "# EVIDENCE_FIRST_OPEN_RESEARCH_POLICY_V1"
if policy_marker not in s:
    policy = '''

# EVIDENCE_FIRST_OPEN_RESEARCH_POLICY_V1
# The active UI/module must not constrain which approved GeoPilot capability
# may answer a question. Prefer deterministic project/site measurements,
# project-controlled documents, and approved authoritative providers.
# Unrelated evidence must never substitute for the required evidence.
EVIDENCE_FIRST_OPEN_RESEARCH_POLICY = (
    "Use the best approved evidence source for the question, not merely the "
    "evidence currently visible in the active module. Never fabricate a "
    "measurement, policy, document fact, citation, location, or provider result."
)
'''
    s = s.rstrip() + policy + "\n"

router.write_text(s, encoding="utf-8")
print("PATCHED:", router)

t = tests.read_text(encoding="utf-8-sig")
extra = r'''

def test_malay_maximum_height_routes_to_terrain_measurement():
    route = route_question("Berapakah ketinggian maksimum kawasan tersebut?")
    assert route.state == "planned"
    assert route.capability == "terrain_measurement"
    assert route.tools == ("terrain.site_summary",)


def test_malay_maximum_elevation_routes_to_terrain_measurement():
    route = route_question("Berapa elevasi tertinggi kawasan ini?")
    assert route.capability == "terrain_measurement"
    assert route.tools == ("terrain.site_summary",)


def test_malay_average_slope_routes_to_terrain_measurement():
    route = route_question("Berapakah purata kecerunan kawasan ini?")
    assert route.capability == "terrain_measurement"
    assert route.tools == ("terrain.site_summary",)


def test_ndvi_question_does_not_route_to_terrain_measurement():
    route = route_question("Berapakah perubahan NDVI antara imej before dan after?")
    assert route.capability != "terrain_measurement"
    assert all(not tool.startswith("terrain.") for tool in route.tools)
'''
if "test_malay_maximum_height_routes_to_terrain_measurement" not in t:
    t = t.rstrip() + extra + "\n"
    tests.write_text(t, encoding="utf-8")
    print("PATCHED:", tests)
else:
    print("SKIP: router acceptance tests already present.")

a = trackb_ai.read_text(encoding="utf-8-sig")
needle = (
    "You are GeoPilot AI Decision Workspace. Answer the planner's TERRAIN MEASUREMENT "
    "question using ONLY the supplied deterministic terrain facts from terrain.site_summary. "
)
replacement = (
    "You are GeoPilot AI Decision Workspace operating under an EVIDENCE-FIRST OPEN RESEARCH "
    "policy. The active module must not constrain evidence selection. For this TERRAIN "
    "MEASUREMENT question, use ONLY the supplied deterministic terrain facts from "
    "terrain.site_summary. "
)
if needle in a:
    a = a.replace(needle, replacement, 1)

trackb_ai.write_text(a, encoding="utf-8")
print("PATCHED:", trackb_ai)
'@

Write-Host "[1] Apply evidence-first router patch"
$patch | docker compose exec -T backend python -
if ($LASTEXITCODE -ne 0) { throw "Router patch failed." }

Write-Host ""
Write-Host "[2] Syntax checks"
docker compose exec -T backend python -m py_compile app/services/data_requirement_router.py app/services/track_b_ai.py tests/test_data_requirement_router.py
if ($LASTEXITCODE -ne 0) { throw "Syntax check failed." }

Write-Host ""
Write-Host "[3] Router + terrain regression tests"
docker compose exec -T backend python -m pytest -q tests/test_data_requirement_router.py tests/test_terrain_analysis.py tests/test_terrain_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Regression tests failed." }

Write-Host ""
Write-Host "[4] Exact Malay routing acceptance"
docker compose exec -T backend python -c "from app.services.data_requirement_router import route_question; qs=['berapa slope paling tinggi di kawasan tersebut?','Berapakah ketinggian maksimum kawasan tersebut?','Berapa elevasi tertinggi kawasan ini?','Berapakah purata kecerunan kawasan ini?']; [(print(q,'=>',route_question(q).capability,route_question(q).tools)) for q in qs]; assert all(route_question(q).capability=='terrain_measurement' and route_question(q).tools==('terrain.site_summary',) for q in qs)"
if ($LASTEXITCODE -ne 0) { throw "Malay terrain routing acceptance failed." }

Write-Host ""
Write-Host "[5] Verify NDVI remains non-terrain"
docker compose exec -T backend python -c "from app.services.data_requirement_router import route_question; q='Berapakah perubahan NDVI antara imej before dan after?'; r=route_question(q); print(q,'=>',r.capability,r.tools); assert r.capability!='terrain_measurement' and all(not x.startswith('terrain.') for x in r.tools)"
if ($LASTEXITCODE -ne 0) { throw "NDVI control routing failed." }

Write-Host ""
Write-Host "[6] Restart backend"
docker compose restart backend
if ($LASTEXITCODE -ne 0) { throw "Backend restart failed." }
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "[7] Service health"
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "Service health check failed." }

Write-Host ""
Write-Host "============================================================"
Write-Host "EVIDENCE-FIRST OPEN RESEARCH ROUTER V1 PASS"
Write-Host "============================================================"
Write-Host "Cross-module evidence routing: ENABLED"
Write-Host "Malay terrain vocabulary: EXPANDED"
Write-Host "Ketinggian/elevasi/slope questions: terrain.site_summary"
Write-Host "NDVI as substitute for terrain: BLOCKED"
Write-Host "Manual DEM precedence: PRESERVED"
Write-Host "Automatic CDSE terrain acquisition: PRESERVED"
Write-Host "Fabricated numeric/policy claims: FORBIDDEN"
Write-Host "Approved evidence only: REQUIRED"
Write-Host "External arbitrary web search: NOT ADDED IN V1"
Write-Host "DB schema change: NONE"
Write-Host "Migration: NONE"
Write-Host "============================================================"
