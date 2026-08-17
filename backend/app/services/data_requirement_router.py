from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RouteState = Literal["planned", "clarification_required", "evidence_required"]


@dataclass(frozen=True)
class DataRequirementPlan:
    state: RouteState
    capability: str
    tools: tuple[str, ...]
    required_evidence: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


_SITE_APPLICABILITY_TERMS = (
    "active site", "this site", "the site", "site", "tapak", "kawasan ini",
    "kawasan", "applicable", "applies", "apply to", "planning block", "bpk",
    "zoning", "zone", "land use", "guna tanah",
)

_SITE_CLASSIFICATION_TERMS = (
    "planning block", "bpk", "zoning", "zone", "land use", "guna tanah",
    "planning area", "subzone", "subzon", "kategori guna tanah",
)
_AREA_TERMS = ("area", "hectare", "hectares", "keluasan")
_TERRAIN_TERMS = (
    "slope", "gradient", "terrain", "topography", "topographic", "elevation",
    "altitude", "contour", "dem", "kecerunan", "cerun", "lereng", "elevasi",
    "ketinggian", "tinggi", "aras tanah", "paras tanah", "kontur", "topografi",
)
_TERRAIN_MEASUREMENT_TERMS = (
    "berapa", "what is", "highest", "lowest", "maximum", "minimum", "max ",
    "min ", "average", "mean", "purata", "tertinggi", "terendah", "nilai",
    "calculate", "measure", "ukur", "kira",
)
_POLICY_TERMS = (
    "policy", "standard", "guideline", "requirement", "allowed", "permitted",
    "statutory", "gpp", "rfn", "rsn", "rkk", "rancangan tempatan",
    "garis panduan", "piawaian", "syarat", "dibenarkan", "had",
)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def route_question(question: str) -> DataRequirementPlan:
    q = " ".join(question.casefold().strip().split())

    if q in {"what is the density?", "what is the density", "berapa density", "density?"}:
        return DataRequirementPlan(
            state="clarification_required",
            capability="density",
            tools=(),
            limitations=(
                "Clarify whether density means a document standard, proposed "
                "density, existing density, population density, units per "
                "hectare, or a category.",
            ),
        )

    terrain = _contains_any(q, _TERRAIN_TERMS)
    terrain_policy = terrain and _contains_any(q, _POLICY_TERMS)
    terrain_measurement = terrain and (
        _contains_any(q, _TERRAIN_MEASUREMENT_TERMS)
        or _contains_any(q, _SITE_APPLICABILITY_TERMS)
    )

    # Policy intent takes precedence over site words such as "applies".
    # Example: "What guideline applies to slope development?" is a
    # controlled document-retrieval question, not a request to measure slope.
    if terrain_policy:
        return DataRequirementPlan(
            state="planned",
            capability="terrain_policy",
            tools=("documents.search",),
        )

    if terrain_measurement:
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
        if _contains_any(q, _SITE_CLASSIFICATION_TERMS):
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

    tools: list[str] = []
    if _contains_any(q, _AREA_TERMS):
        tools.append("gis.site_area")
    if _contains_any(q, _SITE_APPLICABILITY_TERMS):
        tools.append("gis.site_applicability")
    tools.append("documents.search")

    return DataRequirementPlan(
        state="planned",
        capability="planning_general",
        tools=tuple(dict.fromkeys(tools)),
    )

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

