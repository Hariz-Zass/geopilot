from app.services.site_context_acquisition import (
    SiteContextFeature,
)
from app.services.site_context_evidence import (
    select_site_context_evidence,
)


SITE = {
    "type": "Polygon",
    "coordinates": [[
        [101.5000, 3.0000],
        [101.5100, 3.0000],
        [101.5100, 3.0100],
        [101.5000, 3.0100],
        [101.5000, 3.0000],
    ]],
}


def feature(
    *,
    fid,
    lon,
    lat,
    category,
    value,
    name=None,
    tags=None,
):
    props = {
        "category": category,
        "category_value": value,
        "tags": tags or {},
    }

    if name:
        props["name"] = name

    return SiteContextFeature(
        provider="openstreetmap_overpass",
        source_feature_id=fid,
        geometry={
            "type": "Point",
            "coordinates": [lon, lat],
        },
        properties=props,
    )


def test_school_becomes_education():
    result = select_site_context_evidence(
        site_geometry=SITE,
        features=[
            feature(
                fid="node/1",
                lon=101.505,
                lat=3.005,
                category="amenity",
                value="school",
                name="Sekolah Test",
                tags={"amenity": "school"},
            )
        ],
    )

    assert result.selected_feature_count == 1
    item = result.selected[0]

    assert item.planning_category == "education"
    assert item.distance_meters == 0.0


def test_bus_stop_becomes_transport():
    result = select_site_context_evidence(
        site_geometry=SITE,
        features=[
            feature(
                fid="node/2",
                lon=101.511,
                lat=3.005,
                category="highway",
                value="bus_stop",
                name="Bus Stop",
            )
        ],
    )

    assert result.selected[0].planning_category == "transport"


def test_major_road_ranked_above_service_road():
    result = select_site_context_evidence(
        site_geometry=SITE,
        features=[
            feature(
                fid="way/3",
                lon=101.512,
                lat=3.005,
                category="highway",
                value="primary",
                name="Jalan Utama",
            ),
            feature(
                fid="way/4",
                lon=101.512,
                lat=3.005,
                category="highway",
                value="service",
                name="Jalan Servis",
            ),
        ],
    )

    assert result.selected[0].name == "Jalan Utama"


def test_healthcare_classification():
    result = select_site_context_evidence(
        site_geometry=SITE,
        features=[
            feature(
                fid="node/5",
                lon=101.512,
                lat=3.006,
                category="amenity",
                value="clinic",
                name="Klinik Test",
                tags={"amenity": "clinic"},
            )
        ],
    )

    assert result.selected[0].planning_category == "healthcare"


def test_category_limit_is_enforced():
    features = [
        feature(
            fid=f"node/{index}",
            lon=101.511 + index / 10000,
            lat=3.005,
            category="amenity",
            value="school",
            name=f"School {index}",
            tags={"amenity": "school"},
        )
        for index in range(10)
    ]

    result = select_site_context_evidence(
        site_geometry=SITE,
        features=features,
        max_per_category=3,
        max_total=20,
    )

    assert result.category_counts["education"] == 3
    assert result.selected_feature_count == 3


def test_total_limit_is_enforced():
    features = [
        feature(
            fid="node/education",
            lon=101.512,
            lat=3.005,
            category="amenity",
            value="school",
            name="School",
            tags={"amenity": "school"},
        ),
        feature(
            fid="node/health",
            lon=101.512,
            lat=3.006,
            category="amenity",
            value="clinic",
            name="Clinic",
            tags={"amenity": "clinic"},
        ),
        feature(
            fid="node/shop",
            lon=101.512,
            lat=3.007,
            category="shop",
            value="mall",
            name="Mall",
        ),
    ]

    result = select_site_context_evidence(
        site_geometry=SITE,
        features=features,
        max_total=2,
    )

    assert result.selected_feature_count == 2


def test_duplicate_source_id_removed():
    duplicate = feature(
        fid="node/dup",
        lon=101.512,
        lat=3.005,
        category="amenity",
        value="school",
        name="School",
        tags={"amenity": "school"},
    )

    result = select_site_context_evidence(
        site_geometry=SITE,
        features=[
            duplicate,
            duplicate,
        ],
    )

    assert result.source_feature_count == 2
    assert result.eligible_feature_count == 1
    assert result.selected_feature_count == 1


def test_irrelevant_building_is_not_selected():
    result = select_site_context_evidence(
        site_geometry=SITE,
        features=[
            feature(
                fid="way/building",
                lon=101.505,
                lat=3.005,
                category="building",
                value="yes",
            )
        ],
    )

    assert result.eligible_feature_count == 0
    assert result.selected_feature_count == 0


def test_natural_tree_is_not_water():
    result = select_site_context_evidence(
        site_geometry=SITE,
        features=[
            feature(
                fid="node/tree",
                lon=101.512,
                lat=3.005,
                category="natural",
                value="tree",
                name="Pokok",
            )
        ],
    )

    assert result.selected_feature_count == 1
    assert result.selected[0].planning_category == "natural"
    assert result.selected[0].subtype == "tree"


def test_natural_water_is_water():
    result = select_site_context_evidence(
        site_geometry=SITE,
        features=[
            feature(
                fid="way/water",
                lon=101.512,
                lat=3.005,
                category="natural",
                value="water",
                name="Tasik Test",
            )
        ],
    )

    assert result.selected_feature_count == 1
    assert result.selected[0].planning_category == "water"


def test_waterway_drain_is_water():
    result = select_site_context_evidence(
        site_geometry=SITE,
        features=[
            feature(
                fid="way/drain",
                lon=101.512,
                lat=3.005,
                category="waterway",
                value="drain",
                name="Drain Test",
            )
        ],
    )

    assert result.selected_feature_count == 1
    assert result.selected[0].planning_category == "water"
    assert result.selected[0].subtype == "drain"


def test_tourism_hotel_is_not_recreation():
    result = select_site_context_evidence(
        site_geometry=SITE,
        features=[
            feature(
                fid="node/hotel",
                lon=101.512,
                lat=3.005,
                category="tourism",
                value="hotel",
                name="Hotel Test",
            )
        ],
    )

    assert result.selected_feature_count == 1
    assert result.selected[0].planning_category == "tourism"
    assert result.selected[0].subtype == "hotel"


def test_leisure_park_remains_recreation():
    result = select_site_context_evidence(
        site_geometry=SITE,
        features=[
            feature(
                fid="way/park",
                lon=101.512,
                lat=3.005,
                category="leisure",
                value="park",
                name="Taman Test",
            )
        ],
    )

    assert result.selected_feature_count == 1
    assert result.selected[0].planning_category == "recreation"
    assert result.selected[0].subtype == "park"
