from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

from shapely.geometry import shape
from shapely.ops import nearest_points

from app.services.site_context_acquisition import SiteContextFeature


@dataclass(frozen=True)
class SiteContextEvidenceItem:
    source_feature_id: str
    provider: str
    name: str | None
    planning_category: str
    subtype: str | None
    geometry_type: str
    distance_meters: float
    spatial_relation: str
    score: float
    properties: dict[str, Any]


@dataclass(frozen=True)
class SiteContextEvidenceSelectionResult:
    source_feature_count: int
    eligible_feature_count: int
    selected_feature_count: int
    selected: tuple[SiteContextEvidenceItem, ...]
    category_counts: dict[str, int]


_CATEGORY_BASE_SCORE = {
    "education": 100.0,
    "healthcare": 100.0,
    "transport": 95.0,
    "road": 90.0,
    "civic": 88.0,
    "water": 88.0,
    "natural": 82.0,
    "landuse": 82.0,
    "commercial": 75.0,
    "recreation": 72.0,
    "tourism": 70.0,
}

_MAJOR_ROADS = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
}

_EDUCATION = {
    "school",
    "kindergarten",
    "college",
    "university",
    "library",
}

_HEALTHCARE = {
    "hospital",
    "clinic",
    "doctors",
    "dentist",
    "pharmacy",
}

_TRANSPORT_AMENITY = {
    "bus_station",
    "ferry_terminal",
    "taxi",
}

_CIVIC = {
    "townhall",
    "police",
    "fire_station",
    "post_office",
    "courthouse",
    "community_centre",
    "social_facility",
    "place_of_worship",
}

_COMMERCIAL_AMENITY = {
    "bank",
    "marketplace",
    "restaurant",
    "fast_food",
    "food_court",
    "cafe",
}

_RECREATION_AMENITY = {
    "theatre",
    "cinema",
    "arts_centre",
}


def _classify_feature(
    feature: SiteContextFeature,
) -> tuple[str | None, str | None]:
    props = feature.properties or {}

    category = props.get("category")
    value = props.get("category_value")

    category_text = (
        str(category).casefold()
        if category is not None
        else ""
    )

    value_text = (
        str(value).casefold()
        if value is not None
        else ""
    )

    tags = props.get("tags")
    if not isinstance(tags, dict):
        tags = {}

    amenity = str(
        tags.get("amenity") or ""
    ).casefold()

    healthcare = str(
        tags.get("healthcare") or ""
    ).casefold()

    if amenity in _EDUCATION or value_text in _EDUCATION:
        return "education", amenity or value_text

    if (
        category_text == "healthcare"
        or healthcare
        or amenity in _HEALTHCARE
        or value_text in _HEALTHCARE
    ):
        return "healthcare", healthcare or amenity or value_text

    if (
        category_text == "public_transport"
        or category_text == "railway"
        or amenity in _TRANSPORT_AMENITY
    ):
        return "transport", value_text or amenity or category_text

    if category_text == "highway":
        if value_text == "bus_stop":
            return "transport", "bus_stop"

        return "road", value_text or None

    if amenity in _CIVIC or value_text in _CIVIC:
        return "civic", amenity or value_text

    if category_text == "waterway":
        return "water", value_text or None

    if category_text == "natural":
        if value_text in {
            "water",
            "wetland",
            "bay",
            "strait",
            "spring",
        }:
            return "water", value_text or None

        return "natural", value_text or None

    if category_text == "landuse":
        return "landuse", value_text or None

    if (
        category_text in {"shop", "office"}
        or amenity in _COMMERCIAL_AMENITY
    ):
        return "commercial", value_text or amenity or category_text

    if (
        category_text == "leisure"
        or amenity in _RECREATION_AMENITY
    ):
        return "recreation", value_text or amenity or category_text

    if category_text == "tourism":
        return "tourism", value_text or category_text

    return None, None


def _haversine_meters(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:
    radius = 6_371_008.8

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(d_lambda / 2.0) ** 2
    )

    return (
        2.0
        * radius
        * math.asin(min(1.0, math.sqrt(a)))
    )


def _distance_from_site_meters(
    site_geometry: dict[str, Any],
    feature_geometry: dict[str, Any],
) -> tuple[float, str]:
    site = shape(site_geometry)
    feature = shape(feature_geometry)

    if site.is_empty or feature.is_empty:
        raise ValueError("Empty geometry cannot be ranked.")

    if not site.is_valid:
        raise ValueError("Site geometry is invalid.")

    if not feature.is_valid:
        raise ValueError("Feature geometry is invalid.")

    if site.intersects(feature):
        return 0.0, "inside_or_intersecting"

    site_point, feature_point = nearest_points(site, feature)

    distance = _haversine_meters(
        site_point.x,
        site_point.y,
        feature_point.x,
        feature_point.y,
    )

    return distance, "nearby"


def _subtype_bonus(
    planning_category: str,
    subtype: str | None,
) -> float:
    if not subtype:
        return 0.0

    value = subtype.casefold()

    if planning_category == "road" and value in _MAJOR_ROADS:
        return 20.0

    if planning_category == "education":
        return 15.0

    if planning_category == "healthcare":
        return 15.0

    if planning_category == "transport":
        return 12.0

    if planning_category == "civic":
        return 10.0

    return 0.0


def _proximity_score(
    distance_meters: float,
) -> float:
    if distance_meters <= 0:
        return 30.0
    if distance_meters <= 100:
        return 28.0
    if distance_meters <= 250:
        return 24.0
    if distance_meters <= 500:
        return 18.0
    if distance_meters <= 1000:
        return 10.0
    if distance_meters <= 2000:
        return 4.0

    return 0.0


def select_site_context_evidence(
    *,
    site_geometry: dict[str, Any],
    features: Iterable[SiteContextFeature],
    max_per_category: int = 5,
    max_total: int = 40,
) -> SiteContextEvidenceSelectionResult:
    if max_per_category <= 0:
        raise ValueError("max_per_category must be positive.")

    if max_total <= 0:
        raise ValueError("max_total must be positive.")

    source_features = list(features)

    candidates: list[SiteContextEvidenceItem] = []
    seen_ids: set[str] = set()

    for feature in source_features:
        if feature.source_feature_id in seen_ids:
            continue

        seen_ids.add(feature.source_feature_id)

        planning_category, subtype = _classify_feature(feature)

        if planning_category is None:
            continue

        try:
            distance_meters, relation = _distance_from_site_meters(
                site_geometry,
                feature.geometry,
            )
        except Exception:
            continue

        props = feature.properties or {}
        raw_name = props.get("name")

        name = (
            str(raw_name)
            if raw_name not in {None, ""}
            else None
        )

        score = (
            _CATEGORY_BASE_SCORE[planning_category]
            + _subtype_bonus(planning_category, subtype)
            + _proximity_score(distance_meters)
            + (8.0 if name is not None else 0.0)
        )

        candidates.append(
            SiteContextEvidenceItem(
                source_feature_id=feature.source_feature_id,
                provider=feature.provider,
                name=name,
                planning_category=planning_category,
                subtype=subtype,
                geometry_type=str(feature.geometry.get("type")),
                distance_meters=round(distance_meters, 2),
                spatial_relation=relation,
                score=round(score, 2),
                properties=dict(props),
            )
        )

    candidates.sort(
        key=lambda item: (
            -item.score,
            item.distance_meters,
            item.source_feature_id,
        )
    )

    per_category: dict[str, int] = {}
    selected: list[SiteContextEvidenceItem] = []

    for candidate in candidates:
        current = per_category.get(
            candidate.planning_category,
            0,
        )

        if current >= max_per_category:
            continue

        selected.append(candidate)

        per_category[
            candidate.planning_category
        ] = current + 1

        if len(selected) >= max_total:
            break

    return SiteContextEvidenceSelectionResult(
        source_feature_count=len(source_features),
        eligible_feature_count=len(candidates),
        selected_feature_count=len(selected),
        selected=tuple(selected),
        category_counts=dict(per_category),
    )
