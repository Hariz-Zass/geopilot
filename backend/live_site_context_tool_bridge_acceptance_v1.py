import uuid

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.planning_run import PlanningRun
from app.models.user import User
from app.services.isolation import SiteState
from app.services.planning_tools import execute_site_context


TARGET_PROJECT_ID = uuid.UUID(
    "f7617e94-7d8c-47d0-8bed-635cf2f48579"
)

TARGET_SITE_ID = uuid.UUID(
    "2ea1e98d-347c-4a0a-8e5b-5dd7f9553673"
)


print("============================================================")
print("GEOPILOT LIVE SITE CONTEXT TOOL BRIDGE ACCEPTANCE V1")
print("REAL SHAH ALAM SITE + LIVE OSM + TOOL EVIDENCE")
print("============================================================")

SessionFactory = get_session_factory()

with SessionFactory() as session:

    run = session.scalars(
        select(PlanningRun)
        .where(
            PlanningRun.project_id == TARGET_PROJECT_ID,
            PlanningRun.site_id == TARGET_SITE_ID,
        )
        .order_by(PlanningRun.created_at.desc())
    ).first()

    if run is None:
        print("BRIDGE_ACCEPTANCE=BLOCKED")
        print("REASON=NO PROJECT/SITE PLANNING RUN OWNER CONTEXT")
        raise SystemExit(2)

    owner = session.get(
        User,
        run.created_by_user_id,
    )

    if owner is None:
        print("BRIDGE_ACCEPTANCE=BLOCKED")
        print("REASON=PLANNING RUN OWNER NOT FOUND")
        raise SystemExit(2)

    print("OWNER_CONTEXT_FOUND=YES")
    print("PROJECT_ID=" + str(TARGET_PROJECT_ID))
    print("SITE_ID=" + str(TARGET_SITE_ID))

    evidence, limitations = execute_site_context(
        session,
        owner=owner,
        project_id=TARGET_PROJECT_ID,
        site_id=TARGET_SITE_ID,
        site_state=SiteState.AVAILABLE,
    )

    # This acceptance probe must not persist anything.
    session.rollback()

print("DB_WRITE=NO")

print()
print("=== BRIDGE RESULT ===")

print(
    "EVIDENCE_COUNT="
    + str(len(evidence))
)

print(
    "TOOL_LIMITATION_COUNT="
    + str(len(limitations))
)

if not evidence:
    print("BRIDGE_ACCEPTANCE=FAIL")
    print("REASON=ZERO TOOL EVIDENCE")
    raise SystemExit(1)

invalid_tool = []
invalid_status = []
invalid_determinism = []
invalid_source = []
wrong_project = []
wrong_site = []

categories = {}

for item in evidence:

    if item.tool_name != "context.site_surroundings":
        invalid_tool.append(
            str(item.evidence_id)
        )

    if item.status != "retrieved":
        invalid_status.append(
            str(item.evidence_id)
        )

    if item.deterministic is not False:
        invalid_determinism.append(
            str(item.evidence_id)
        )

    if str(item.project_id) != str(TARGET_PROJECT_ID):
        wrong_project.append(
            str(item.evidence_id)
        )

    if str(item.site_id) != str(TARGET_SITE_ID):
        wrong_site.append(
            str(item.evidence_id)
        )

    if (
        len(item.sources) != 1
        or item.sources[0].kind
        != "external_provider"
    ):
        invalid_source.append(
            str(item.evidence_id)
        )

    category = str(
        item.payload.get(
            "planning_category"
        )
    )

    categories[category] = (
        categories.get(category, 0)
        + 1
    )

print(
    "CATEGORY_COUNTS="
    + str(categories)
)

print(
    "INVALID_TOOL_COUNT="
    + str(len(invalid_tool))
)

print(
    "INVALID_STATUS_COUNT="
    + str(len(invalid_status))
)

print(
    "INVALID_DETERMINISM_COUNT="
    + str(len(invalid_determinism))
)

print(
    "INVALID_SOURCE_COUNT="
    + str(len(invalid_source))
)

print(
    "WRONG_PROJECT_COUNT="
    + str(len(wrong_project))
)

print(
    "WRONG_SITE_COUNT="
    + str(len(wrong_site))
)

print()
print("=== SAMPLE TOOL EVIDENCE ===")

for index, item in enumerate(
    evidence[:10],
    start=1,
):

    print(
        f"SAMPLE_{index}_CATEGORY="
        + str(
            item.payload.get(
                "planning_category"
            )
        )
    )

    print(
        f"SAMPLE_{index}_NAME="
        + str(
            item.payload.get("name")
        )
    )

    print(
        f"SAMPLE_{index}_DISTANCE_M="
        + str(
            item.payload.get(
                "distance_meters"
            )
        )
    )

    print(
        f"SAMPLE_{index}_SOURCE_KIND="
        + item.sources[0].kind
    )

    print(
        f"SAMPLE_{index}_SOURCE_ID="
        + str(item.sources[0].id)
    )

if (
    invalid_tool
    or invalid_status
    or invalid_determinism
    or invalid_source
    or wrong_project
    or wrong_site
):
    print()
    print("BRIDGE_ACCEPTANCE=FAIL")
    raise SystemExit(1)

print()
print("BRIDGE_ACCEPTANCE=PASS")
