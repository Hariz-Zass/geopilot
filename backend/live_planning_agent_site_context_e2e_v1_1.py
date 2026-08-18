import uuid
import traceback

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.planning_run import PlanningRun
from app.models.user import User
from app.schemas.planning_run import PlanningRunCreate
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

created_run_id = None


print("============================================================")
print("GEOPILOT LIVE PLANNING AGENT SITE CONTEXT E2E V1.1")
print("REAL SHAH ALAM SITE + LIVE OSM + AI SYNTHESIS")
print("CONTROLLED TEMPORARY PLANNING RUN + CLEANUP")
print("============================================================")


SessionFactory = get_session_factory()

try:
    with SessionFactory() as session:

        # -----------------------------------------------------
        # Resolve an existing authorized owner context.
        # -----------------------------------------------------

        source_run = session.scalars(
            select(PlanningRun)
            .where(
                PlanningRun.project_id == PROJECT_ID,
                PlanningRun.site_id == SITE_ID,
            )
            .order_by(PlanningRun.created_at.desc())
        ).first()

        if source_run is None:
            raise RuntimeError(
                "No existing PlanningRun owner context "
                "was found for the target project/site."
            )

        owner = session.get(
            User,
            source_run.created_by_user_id,
        )

        if owner is None:
            raise RuntimeError(
                "Owner referenced by existing PlanningRun "
                "could not be resolved."
            )

        print("OWNER_CONTEXT_FOUND=YES")
        print("OWNER_ID=" + str(owner.id))
        print("PROJECT_ID=" + str(PROJECT_ID))
        print("SITE_ID=" + str(SITE_ID))

        # -----------------------------------------------------
        # Create real PlanningRun using exact production contract.
        # -----------------------------------------------------

        request = PlanningRunCreate(
            question=QUESTION,
            development_intent=None,
        )

        run = create_planning_run(
            session,
            owner=owner,
            project_id=PROJECT_ID,
            site_id=SITE_ID,
            request=request,
            site_state=SiteState.AVAILABLE,
        )

        created_run_id = run.id

        print()
        print("TEMP_RUN_CREATED=YES")
        print("RUN_ID=" + str(run.id))
        print("QUESTION=" + str(run.question))

        # -----------------------------------------------------
        # Execute through real Planning Agent orchestrator.
        # -----------------------------------------------------

        run = execute_planning_run(
            session,
            owner=owner,
            project_id=PROJECT_ID,
            site_id=SITE_ID,
            run_id=run.id,
            site_state=SiteState.AVAILABLE,
        )

        session.refresh(run)

        print()
        print("=== ORCHESTRATOR RESULT ===")
        print("STATUS=" + str(run.status))
        print("PLAN=" + repr(run.plan))
        print("LIMITATIONS=" + repr(run.limitations))

        evidence = run.evidence or []

        context_items = [
            item
            for item in evidence
            if isinstance(item, dict)
            and item.get("tool_name")
            == "context.site_surroundings"
        ]

        print(
            "TOTAL_EVIDENCE_COUNT="
            + str(len(evidence))
        )

        print(
            "CONTEXT_EVIDENCE_COUNT="
            + str(len(context_items))
        )

        categories = {}

        for item in context_items:
            payload = item.get("payload") or {}

            category = payload.get(
                "planning_category"
            )

            categories[str(category)] = (
                categories.get(str(category), 0) + 1
            )

        print(
            "CONTEXT_CATEGORY_COUNTS="
            + repr(categories)
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
            payload = item.get("payload") or {}
            sources = item.get("sources") or []

            print(
                f"EDU_{index}_NAME="
                + str(payload.get("name"))
            )

            print(
                f"EDU_{index}_SUBTYPE="
                + str(payload.get("subtype"))
            )

            print(
                f"EDU_{index}_DISTANCE_M="
                + str(payload.get("distance_meters"))
            )

            print(
                f"EDU_{index}_RELATION="
                + str(payload.get("spatial_relation"))
            )

            if sources:
                print(
                    f"EDU_{index}_SOURCE_KIND="
                    + str(sources[0].get("kind"))
                )

                print(
                    f"EDU_{index}_SOURCE_ID="
                    + str(sources[0].get("id"))
                )

        print()
        print("=== AI ANSWER ===")
        print(str(run.synthesis))

        # -----------------------------------------------------
        # Acceptance assertions.
        # -----------------------------------------------------

        failures = []

        plan = run.plan or []

        if "context.site_surroundings" not in plan:
            failures.append(
                "Router/orchestrator plan did not include "
                "context.site_surroundings."
            )

        if not context_items:
            failures.append(
                "No context.site_surroundings ToolEvidence "
                "was persisted on the PlanningRun."
            )

        if not education_items:
            failures.append(
                "No education evidence was selected."
            )

        invalid_sources = []

        for item in context_items:
            sources = item.get("sources") or []

            if not sources:
                invalid_sources.append(
                    "missing_source"
                )
                continue

            if sources[0].get("kind") != "external_provider":
                invalid_sources.append(
                    str(sources[0].get("kind"))
                )

        if invalid_sources:
            failures.append(
                "Invalid context provenance: "
                + repr(invalid_sources)
            )

        if not run.synthesis or not str(run.synthesis).strip():
            failures.append(
                "Planning Agent produced no AI answer."
            )

        if str(run.status) not in {
            "completed",
            "degraded",
        }:
            failures.append(
                "Unexpected PlanningRun status: "
                + str(run.status)
            )

        print()
        print("=== ACCEPTANCE ===")

        if failures:
            for failure in failures:
                print("FAILURE=" + failure)

            print("E2E_ACCEPTANCE=FAIL")

        else:
            print("ROUTER_TO_CONTEXT_TOOL=PASS")
            print("LIVE_CONTEXT_ACQUISITION=PASS")
            print("TOOL_EVIDENCE_BRIDGE=PASS")
            print("EXTERNAL_PROVIDER_PROVENANCE=PASS")
            print("EDUCATION_EVIDENCE=PASS")
            print("AI_SYNTHESIS=PASS")
            print("E2E_ACCEPTANCE=PASS")

        # -----------------------------------------------------
        # Controlled cleanup.
        # -----------------------------------------------------

        session.delete(run)
        session.commit()

        print()
        print("TEMP_RUN_CLEANUP=PASS")
        print("DB_TEST_RUN_RETAINED=NO")

        if failures:
            raise SystemExit(1)


except SystemExit:
    raise

except Exception as exc:

    print()
    print("E2E_ACCEPTANCE=BLOCKED")
    print(
        "ERROR="
        + type(exc).__name__
        + ": "
        + str(exc)
    )

    traceback.print_exc()

    # Best-effort cleanup if the run was committed before failure.
    if created_run_id is not None:
        try:
            with SessionFactory() as cleanup_session:

                cleanup_run = cleanup_session.get(
                    PlanningRun,
                    created_run_id,
                )

                if cleanup_run is not None:
                    cleanup_session.delete(cleanup_run)
                    cleanup_session.commit()

                print("TEMP_RUN_CLEANUP=PASS")
                print("DB_TEST_RUN_RETAINED=NO")

        except Exception as cleanup_exc:
            print(
                "TEMP_RUN_CLEANUP=FAIL: "
                + type(cleanup_exc).__name__
                + ": "
                + str(cleanup_exc)
            )

    raise SystemExit(2)
