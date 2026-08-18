from pathlib import Path

ROOT = Path("/app/app")
router = ROOT / "services" / "data_requirement_router.py"
trackb = ROOT / "api" / "v1" / "track_b.py"

def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}_COUNT_{count}")
    return text.replace(old, new, 1)

t = router.read_text(encoding="utf-8-sig")

old = '''    if terrain_measurement:
        return DataRequirementPlan(
            state="planned",
            capability="terrain_measurement",
            tools=("terrain.site_summary",),
            required_evidence=("project_site_dem_or_elevation_raster",),
            limitations=(
                "Terrain measurement requires a project/site-scoped DEM or "
                "elevation raster.",
                "Slope or elevation must not be inferred from NDVI, the visual "
                "basemap, satellite change geometry, or Site geometry.",
            ),
        )

    tools: list[str] = []
'''

new = '''    if terrain_measurement:
        terrain_requirements = ("project_site_dem_or_elevation_raster",)
        terrain_limitations = (
            "Terrain measurement requires a project/site-scoped DEM or "
            "elevation raster.",
            "Slope or elevation must not be inferred from NDVI, the visual "
            "basemap, satellite change geometry, or Site geometry.",
        )

        if _contains_any(q, _AREA_TERMS):
            return DataRequirementPlan(
                state="planned",
                capability="planning_multi_evidence",
                tools=("gis.site_area", "terrain.site_summary"),
                required_evidence=terrain_requirements,
                limitations=terrain_limitations,
            )

        return DataRequirementPlan(
            state="planned",
            capability="terrain_measurement",
            tools=("terrain.site_summary",),
            required_evidence=terrain_requirements,
            limitations=terrain_limitations,
        )

    tools: list[str] = []
'''

t = replace_once(t, old, new, "ROUTER_TERRAIN_BLOCK")
router.write_text(t, encoding="utf-8")

t = trackb.read_text(encoding="utf-8-sig")
old = '        if route is not None and "documents.search" in route.tools:\n'
new = '''        if route is not None and (
            route.capability == "planning_multi_evidence"
            or "documents.search" in route.tools
        ):
'''
t = replace_once(t, old, new, "TRACKB_ORCHESTRATOR_DISPATCH")
trackb.write_text(t, encoding="utf-8")

print("PATCHED data_requirement_router.py")
print("PATCHED track_b.py")