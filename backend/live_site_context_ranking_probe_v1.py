import json
import uuid

from sqlalchemy import select, func

from app.db.session import get_session_factory
from app.models.site import Site
from app.services.site_context_acquisition import (
    OpenStreetMapOverpassProvider,
)
from app.services.site_context_evidence import (
    select_site_context_evidence,
)

TARGET_SITE_ID = uuid.UUID(
    "2ea1e98d-347c-4a0a-8e5b-5dd7f9553673"
)

print("============================================================")
print("GEOPILOT LIVE SITE CONTEXT RANKING ACCEPTANCE V1")
print("REAL SHAH ALAM SITE + LIVE OSM + EVIDENCE RANKING")
print("READ ONLY - NO DB WRITE")
print("============================================================")
print()

SessionFactory = get_session_factory()

with SessionFactory() as session:
    site = session.get(
        Site,
        TARGET_SITE_ID,
    )

    print(
        "SITE_FOUND="
        + str(site is not None)
    )

    if site is None:
        print("RANKING_ACCEPTANCE=BLOCKED")
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
        print("RANKING_ACCEPTANCE=BLOCKED")
        print("REASON=SITE GEOMETRY UNAVAILABLE")
        raise SystemExit(2)

    geometry = json.loads(
        geometry_json
    )

    print(
        "GEOMETRY_TYPE="
        + str(geometry.get("type"))
    )

    session.rollback()

print("DB_WRITE=NO")

print()
print("=== LIVE ACQUISITION ===")

provider = OpenStreetMapOverpassProvider(
    timeout_seconds=90.0,
)

acquisition = provider.acquire(
    site_geometry=geometry,
    buffer_meters=1000.0,
    max_features=1000,
)

print(
    "RAW_ELEMENT_COUNT="
    + str(acquisition.raw_element_count)
)

print(
    "NORMALIZED_FEATURE_COUNT="
    + str(len(acquisition.features))
)

print(
    "TRUNCATED="
    + str(acquisition.truncated)
)

if not acquisition.features:
    print("RANKING_ACCEPTANCE=BLOCKED")
    print("REASON=ZERO FEATURES")
    raise SystemExit(2)

print()
print("=== EVIDENCE SELECTION ===")

selection = select_site_context_evidence(
    site_geometry=geometry,
    features=acquisition.features,
    max_per_category=5,
    max_total=40,
)

print(
    "SOURCE_FEATURE_COUNT="
    + str(selection.source_feature_count)
)

print(
    "ELIGIBLE_FEATURE_COUNT="
    + str(selection.eligible_feature_count)
)

print(
    "SELECTED_FEATURE_COUNT="
    + str(selection.selected_feature_count)
)

print(
    "CATEGORY_COUNTS="
    + str(selection.category_counts)
)

print()
print("=== SELECTED EVIDENCE ===")

for index, item in enumerate(
    selection.selected,
    start=1,
):
    print(
        f"EVIDENCE_{index}_CATEGORY="
        + item.planning_category
    )

    print(
        f"EVIDENCE_{index}_NAME="
        + str(item.name)
    )

    print(
        f"EVIDENCE_{index}_SUBTYPE="
        + str(item.subtype)
    )

    print(
        f"EVIDENCE_{index}_DISTANCE_M="
        + str(item.distance_meters)
    )

    print(
        f"EVIDENCE_{index}_RELATION="
        + item.spatial_relation
    )

    print(
        f"EVIDENCE_{index}_SCORE="
        + str(item.score)
    )

    print(
        f"EVIDENCE_{index}_SOURCE="
        + item.source_feature_id
    )

print()
print("RANKING_ACCEPTANCE=PASS")
