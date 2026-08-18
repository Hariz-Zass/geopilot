from pathlib import Path

p = Path("/app/app/services/data_requirement_router.py")
t = p.read_text(encoding="utf-8-sig")

if '_SITE_CLASSIFICATION_TERMS' in t:
    raise SystemExit('V1_2_ALREADY_PRESENT')

anchor = '_SITE_APPLICABILITY_TERMS = (\n    "active site", "this site", "the site", "site", "tapak", "kawasan ini",\n    "kawasan", "applicable", "applies", "apply to", "planning block", "bpk",\n    "zoning", "zone", "land use", "guna tanah",\n)\n'
addition = '\n_SITE_CLASSIFICATION_TERMS = (\n    "planning block", "bpk", "zoning", "zone", "land use", "guna tanah",\n    "planning area", "subzone", "subzon", "kategori guna tanah",\n)\n'
if anchor not in t:
    raise SystemExit('CLASSIFICATION_ANCHOR_NOT_FOUND')
t = t.replace(anchor, anchor + addition, 1)

old = '        if _contains_any(q, _AREA_TERMS):\n            return DataRequirementPlan(\n                state="planned",\n                capability="planning_multi_evidence",\n                tools=("gis.site_area", "terrain.site_summary"),\n                required_evidence=terrain_requirements,\n                limitations=terrain_limitations,\n            )\n\n        return DataRequirementPlan(\n            state="planned",\n            capability="terrain_measurement",\n            tools=("terrain.site_summary",),\n            required_evidence=terrain_requirements,\n            limitations=terrain_limitations,\n        )\n'
new = '        mixed_tools: list[str] = []\n        if _contains_any(q, _AREA_TERMS):\n            mixed_tools.append("gis.site_area")\n        mixed_tools.append("terrain.site_summary")\n        if _contains_any(q, _SITE_CLASSIFICATION_TERMS):\n            mixed_tools.append("gis.site_applicability")\n            mixed_tools.append("documents.search")\n\n        mixed_tools = list(dict.fromkeys(mixed_tools))\n\n        if mixed_tools != ["terrain.site_summary"]:\n            return DataRequirementPlan(\n                state="planned",\n                capability="planning_multi_evidence",\n                tools=tuple(mixed_tools),\n                required_evidence=terrain_requirements,\n                limitations=terrain_limitations,\n            )\n\n        return DataRequirementPlan(\n            state="planned",\n            capability="terrain_measurement",\n            tools=("terrain.site_summary",),\n            required_evidence=terrain_requirements,\n            limitations=terrain_limitations,\n        )\n'
if old not in t:
    raise SystemExit('V1_TERRAIN_MULTI_BLOCK_NOT_FOUND')
t = t.replace(old, new, 1)

p.write_text(t, encoding="utf-8")
print("PATCHED data_requirement_router.py")