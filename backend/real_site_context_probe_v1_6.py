import json
import traceback
import uuid

from sqlalchemy import select, func

from app.db.session import get_session_factory
from app.models.site import Site
from app.services.site_context_acquisition import (
    OpenStreetMapOverpassProvider,
)

TARGET_SITE_ID = uuid.UUID(
    "2ea1e98d-347c-4a0a-8e5b-5dd7f9553673"
)

print("============================================================")
print("GEOPILOT REAL SITE CONTEXT ACQUISITION V1.6")
print("POSTGIS GEOJSON + LIVE OVERPASS + READ ONLY")
print("============================================================")
print()
print("PROBE_START=YES")

try:
    SessionFactory = get_session_factory()

    with SessionFactory() as session:

        site = session.get(
            Site,
            TARGET_SITE_ID,
        )

        print("TARGET_SITE_ID=" + str(TARGET_SITE_ID))
        print("SITE_FOUND=" + str(site is not None))

        if site is None:
            print("REAL_SITE_CONTEXT_ACQUISITION=BLOCKED")
            print("REASON=TARGET SITE NOT FOUND")
            raise SystemExit(2)

        print("SITE_NAME=" + str(site.name))
        print("PROJECT_ID=" + str(site.project_id))

        geometry_json = session.scalar(
            select(
                func.ST_AsGeoJSON(
                    Site.geometry
                )
            ).where(
                Site.id == TARGET_SITE_ID
            )
        )

        if not geometry_json:
            print("REAL_SITE_CONTEXT_ACQUISITION=BLOCKED")
            print("REASON=SITE GEOMETRY GEOJSON UNAVAILABLE")
            raise SystemExit(2)

        geometry = json.loads(
            geometry_json
        )

        print(
            "GEOJSON_GEOMETRY_TYPE="
            + str(geometry.get("type"))
        )

        coords = geometry.get(
            "coordinates"
        )

        print(
            "GEOJSON_COORDINATES_PRESENT="
            + str(bool(coords))
        )

        session.rollback()

    print("DB_TRANSACTION=ROLLBACK")
    print("DB_SESSION_CLOSED=YES")
    print("DB_WRITE=NO")

    print()
    print("=== LIVE OVERPASS ACQUISITION ===")

    provider = OpenStreetMapOverpassProvider(
        timeout_seconds=90.0,
    )

    result = provider.acquire(
        site_geometry=geometry,
        buffer_meters=1000.0,
        max_features=500,
    )

    print(
        "PROVIDER="
        + str(result.provider)
    )

    print(
        "SOURCE_URI="
        + str(result.source_uri)
    )

    print(
        "QUERY_BBOX="
        + str(result.query_bbox)
    )

    print(
        "BUFFER_METERS="
        + str(result.buffer_meters)
    )

    print(
        "RAW_ELEMENT_COUNT="
        + str(result.raw_element_count)
    )

    print(
        "NORMALIZED_FEATURE_COUNT="
        + str(len(result.features))
    )

    print(
        "TRUNCATED="
        + str(result.truncated)
    )

    if not result.features:
        print("REAL_SITE_CONTEXT_ACQUISITION=BLOCKED")
        print("REASON=ZERO NORMALIZED FEATURES")
        raise SystemExit(2)

    category_counts = {}

    for feature in result.features:
        category = (
            feature.properties.get("category")
            or "uncategorized"
        )

        category_counts[category] = (
            category_counts.get(category, 0)
            + 1
        )

    print()
    print("=== CATEGORY COUNTS ===")

    for category in sorted(category_counts):
        print(
            "CATEGORY_"
            + category.upper()
            + "="
            + str(category_counts[category])
        )

    named = [
        feature
        for feature in result.features
        if feature.properties.get("name")
    ]

    print()
    print(
        "NAMED_FEATURE_COUNT="
        + str(len(named))
    )

    print()
    print("=== NAMED FEATURE SAMPLES ===")

    for index, feature in enumerate(
        named[:30],
        start=1,
    ):
        props = feature.properties

        print(
            f"FEATURE_{index}_ID="
            + str(feature.source_feature_id)
        )
        print(
            f"FEATURE_{index}_NAME="
            + str(props.get("name"))
        )
        print(
            f"FEATURE_{index}_CATEGORY="
            + str(props.get("category"))
        )
        print(
            f"FEATURE_{index}_VALUE="
            + str(props.get("category_value"))
        )
        print(
            f"FEATURE_{index}_GEOMETRY="
            + str(feature.geometry.get("type"))
        )

    print()
    print("REAL_SITE_CONTEXT_ACQUISITION=PASS")

except SystemExit:
    raise

except Exception as exc:
    print()
    print("REAL_SITE_CONTEXT_ACQUISITION=FAIL")
    print(
        "ERROR_TYPE="
        + type(exc).__name__
    )
    print(
        "ERROR="
        + repr(exc)
    )

    print()
    print("=== TRACEBACK ===")
    traceback.print_exc()

    raise SystemExit(1)
