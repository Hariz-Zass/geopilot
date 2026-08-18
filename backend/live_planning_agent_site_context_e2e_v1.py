import uuid

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.planning_run import PlanningRun
from app.models.user import User
from app.services.planning_runs import create_planning_run
from app.services.planning_orchestrator import execute_planning_run
from app.services.isolation import SiteState


PROJECT_ID = uuid.UUID(
    "f7617e94-7d8c-47d0-8bed-635cf2f48579"
)

SITE_ID = uuid.UUID(
    "2ea1e98d-347c-4a0a-8e5b-5dd7f9553673"
)

QUESTION = (
    "Apakah kemudahan pendidikan berhampiran tapak ini?"
)


print("============================================================")
print("GEOPILOT LIVE PLANNING AGENT SITE CONTEXT E2E V1")
print("REAL SHAH ALAM SITE + LIVE OSM + AI SYNTHESIS")
print("============================================================")

SessionFactory = get_session_factory()

with SessionFactory() as session:

    source_run = session.scalars(
        select(PlanningRun)
        .where(
            PlanningRun.project_id == PROJECT_ID,
            PlanningRun.site_id == SITE_ID,
        )
        .order_by(PlanningRun.created_at.desc())
    ).first()

    if source_run is None:
        print("E2E_ACCEPTANCE=BLOCKED")
        print("REASON=NO OWNER CONTEXT FOUND")
        raise SystemExit(2)

    owner = session.get(
        User,
        source_run.created_by_user_id,
    )

    if owner is None:
        print("E2E_ACCEPTANCE=BLOCKED")
        print("REASON=OWNER NOT FOUND")
        raise SystemExit(2)

    run = create_planning_run(
        session,
        owner=owner,
        project_id=PROJECT_ID,
        site_id=SITE_ID,
        question=QUESTION,
    )

    run = execute_planning_run(
        session,
        owner=owner,
        project_id=PROJECT_ID,
        site_id=SITE_ID,
        run_id=run.id,
        site_state=SiteState.AVAILABLE,
    )

    print("RUN_ID=" + str(run.id))
    print("STATUS=" + str(run.status))
    print("PLAN=" + repr(run.plan))

    evidence = run.evidence or []

    context_items = [
        item
        for item in evidence
        if isinstance(item, dict)
        and item.get("tool_name")
        == "context.site_surroundings"
    ]

    print(
        "CONTEXT_EVIDENCE_COUNT="
        + str(len(context_items))
    )

    categories = {}

    for item in context_items:
        payload = item.get("payload") or {}
        category = str(
            payload.get("planning_category")
        )

        categories[category] = (
            categories.get(category, 0) + 1
        )

    print(
        "CONTEXT_CATEGORY_COUNTS="
        + str(categories)
    )

    education_items = [
        item
        for item in context_items
        if (
            (item.get("payload") or {}).get(
                "planning_category"
            )
            == "education"
        )
    ]

    print(
        "EDUCATION_EVIDENCE_COUNT="
        + str(len(education_items))
    )

    print()
    print("=== EDUCATION EVIDENCE ===")

    for index, item in enumerate(
        education_items,
        start=1,
    ):
        payload = item["payload"]

        print(
            f"EDU_{index}_NAME="
            + str(payload.get("name"))
        )

        print(
            f"EDU_{index}_DISTANCE_M="
            + str(
                payload.get(
                    "distance_meters"
                )
            )
        )

        print(
            f"EDU_{index}_RELATION="
            + str(
                payload.get(
                    "spatial_relation"
                )
            )
        )

    print()
    print("=== AI ANSWER ===")
    print(str(run.answer))

    if run.status not in {
        "completed",
        "degraded",
    }:
        print("E2E_ACCEPTANCE=FAIL")
        print("REASON=UNEXPECTED RUN STATUS")
        raise SystemExit(1)

    if not context_items:
        print("E2E_ACCEPTANCE=FAIL")
        print("REASON=NO SITE CONTEXT EVIDENCE")
        raise SystemExit(1)

    if not education_items:
        print("E2E_ACCEPTANCE=FAIL")
        print("REASON=NO EDUCATION EVIDENCE")
        raise SystemExit(1)

    if not run.answer:
        print("E2E_ACCEPTANCE=FAIL")
        print("REASON=NO AI ANSWER")
        raise SystemExit(1)

    print()
    print("E2E_ACCEPTANCE=PASS")
