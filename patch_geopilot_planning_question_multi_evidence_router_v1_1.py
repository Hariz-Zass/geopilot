from pathlib import Path

router = Path("/app/app/services/data_requirement_router.py")

def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}_COUNT_{count}")
    return text.replace(old, new, 1)

t = router.read_text(encoding="utf-8-sig")

old = '''    if terrain_measurement:
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
'''

new = '''    if terrain_measurement:
        terrain_requirements = ("project_site_dem_or_elevation_raster",)
        terrain_limitations = (
            "Terrain measurement requires a project/site-scoped DEM or "
            "elevation raster.",
            "Slope or elevation must not be inferred from NDVI, the visual "
            "basemap, satellite change geometry, or Site geometry.",
        )

        mixed_tools: list[str] = []
        if _contains_any(q, _AREA_TERMS):
            mixed_tools.append("gis.site_area")
        mixed_tools.append("terrain.site_summary")
        if _contains_any(q, _SITE_APPLICABILITY_TERMS):
            mixed_tools.append("gis.site_applicability")
            mixed_tools.append("documents.search")

        mixed_tools = list(dict.fromkeys(mixed_tools))

        if mixed_tools != ["terrain.site_summary"]:
            return DataRequirementPlan(
                state="planned",
                capability="planning_multi_evidence",
                tools=tuple(mixed_tools),
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
'''

t = replace_once(t, old, new, "ROUTER_MULTI_EVIDENCE_BLOCK")
router.write_text(t, encoding="utf-8")
print("PATCHED data_requirement_router.py")