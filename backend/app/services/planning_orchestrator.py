from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.planning_document import PlanningDocument
from app.models.user import User
from app.schemas.document_retrieval import (
    DocumentSearchRequest,
)
from app.schemas.tool_evidence import (
    EvidenceSourceRef,
    ToolEvidence,
)
from app.services.ai_providers import (
    AIProviderError,
    OllamaPlanningProvider,
    OpenAIPlanningProvider,
)
from app.services.document_retrieval import (
    search_documents,
)
from app.services.data_requirement_router import route_question
from app.services.grounded_synthesis import (
    GroundingError,
    evidence_context,
    validate_synthesis,
)
from app.services.planning_document_auto_research import auto_research_planning_documents
from app.services.isolation import SiteState
from app.services.planning_runs import (
    get_planning_run,
    save_run_state,
)
from app.services.planning_tools import (
    execute_latest_temporal_ndvi,
    execute_site_applicability,
    execute_site_area,
    execute_site_context,
    execute_site_terrain_summary,
)
from app.services.terrain_analysis import TerrainEvidenceMissing



class OrchestratorError(Exception):
    pass


_SITE_APPLICABILITY_TERMS = (
    "active site",
    "this site",
    "the site",
    "site",
    "applicable",
    "applies",
    "apply to",
    "planning block",
    "bpk",
    "zoning",
    "zone",
    "land use",
    "guna tanah",
)


def _plan(
    question: str,
) -> tuple[str, list[str]]:
    route = route_question(question)
    return route.state, list(route.tools)


def _scalar_search_values(
    value: Any,
) -> list[str]:
    values: list[str] = []

    if value is None or isinstance(
        value,
        bool,
    ):
        return values

    if isinstance(
        value,
        (str, int, float),
    ):
        text = str(value).strip()

        if (
            1 <= len(text) <= 120
            and text not in {"0", "0.0"}
        ):
            values.append(text)

        return values

    if isinstance(value, dict):
        for nested in value.values():
            values.extend(
                _scalar_search_values(
                    nested
                )
            )

    elif isinstance(value, list):
        for nested in value:
            values.extend(
                _scalar_search_values(
                    nested
                )
            )

    return values


def _spatial_search_terms(
    evidence: list[ToolEvidence],
) -> list[str]:
    terms: list[str] = []

    for item in evidence:
        if (
            item.tool_name
            != "gis.site_applicability"
        ):
            continue

        payload = item.payload

        role = payload.get(
            "applicability_role"
        )
        layer_name = payload.get(
            "layer_name"
        )
        source_feature_id = payload.get(
            "source_feature_id"
        )
        properties = payload.get(
            "properties"
        )

        candidates: list[Any] = [
            role,
            layer_name,
            source_feature_id,
            properties,
        ]

        for candidate in candidates:
            terms.extend(
                _scalar_search_values(
                    candidate
                )
            )

    unique: list[str] = []
    seen: set[str] = set()

    for term in terms:
        key = term.casefold()

        if key in seen:
            continue

        seen.add(key)
        unique.append(term)

        if len(unique) >= 16:
            break

    return unique


def _validate_spatial_classification_answer(
    question: str,
    text: str,
    evidence: list[ToolEvidence],
) -> None:
    q = question.casefold()

    classification_terms = (
        "zoning",
        "zone",
        "land use",
        "guna tanah",
        "planning block",
        "bpk",
    )

    if not any(term in q for term in classification_terms):
        return

    spatial_items = [
        item
        for item in evidence
        if (
            item.tool_name == "gis.site_applicability"
            and item.status == "measured"
        )
    ]

    if not spatial_items:
        return

    low = text.casefold()

    for item in spatial_items:
        payload = item.payload
        properties = payload.get("properties", {})

        landuse_type = properties.get("landuse_type")
        landuse_code = properties.get("landuse_code")
        bp_code = properties.get("bp_code")

        if (
            isinstance(landuse_type, str)
            and landuse_type.strip()
            and landuse_type.casefold() not in low
        ):
            raise GroundingError(
                "Synthesis omitted the deterministic "
                "GIS zoning classification."
            )

        if (
            isinstance(landuse_code, str)
            and landuse_code.strip()
            and landuse_code.casefold() not in low
        ):
            raise GroundingError(
                "Synthesis omitted the deterministic "
                "GIS zoning code."
            )

        if (
            isinstance(bp_code, str)
            and bp_code.strip()
            and bp_code.casefold() not in low
        ):
            raise GroundingError(
                "Synthesis omitted the deterministic "
                "GIS planning-block identity."
            )




def _normalize_document_identity(
    value: str,
) -> str:
    return " ".join(
        value.casefold().split()
    )


def _applicable_document_ids(
    session: Session,
    *,
    project_id: uuid.UUID,
    spatial_evidence: list[ToolEvidence],
) -> tuple[list[uuid.UUID], list[str]]:
    """
    Resolve planning documents explicitly identified by
    deterministic GIS provenance.

    Prefer immutable planning_document_id lineage.
    Fall back to legacy planning_document title identity.
    Fail closed when declared lineage cannot be resolved.
    """
    document_ids: list[uuid.UUID] = []
    references: list[str] = []

    for item in spatial_evidence:
        if item.tool_name != "gis.site_applicability":
            continue

        provenance = (
            item.payload.get("layer_provenance")
            or {}
        )

        raw_document_id = provenance.get(
            "planning_document_id"
        )

        if raw_document_id:
            try:
                document_ids.append(
                    uuid.UUID(str(raw_document_id))
                )
            except (ValueError, TypeError, AttributeError):
                return [], [
                    (
                        "Deterministic GIS evidence contains "
                        "an invalid planning_document_id; "
                        "document retrieval was blocked."
                    )
                ]
            continue

        value = provenance.get(
            "planning_document"
        )

        if isinstance(value, str):
            cleaned = " ".join(
                value.split()
            )

            if cleaned:
                references.append(cleaned)

    document_ids = list(
        dict.fromkeys(document_ids)
    )
    references = list(
        dict.fromkeys(references)
    )

    if document_ids:
        matched_ids = list(
            session.scalars(
                select(PlanningDocument.id).where(
                    PlanningDocument.project_id
                    == project_id,
                    PlanningDocument.id.in_(
                        document_ids
                    ),
                    PlanningDocument.is_archived.is_(
                        False
                    ),
                )
            )
        )

        if set(matched_ids) != set(document_ids):
            return [], [
                (
                    "Deterministic GIS evidence references "
                    "a planning_document_id that is missing, "
                    "archived, or outside the active project; "
                    "document retrieval was blocked."
                )
            ]

        return matched_ids, []

    if not references:
        return [], [
            (
                "Spatial applicability evidence does not "
                "declare an explicit planning_document_id "
                "or planning_document identity; document "
                "applicability could not be resolved."
            )
        ]

    documents = list(
        session.scalars(
            select(PlanningDocument).where(
                PlanningDocument.project_id
                == project_id,
                PlanningDocument.is_archived.is_(
                    False
                ),
            )
        )
    )

    matched: list[uuid.UUID] = []

    for document in documents:
        title = _normalize_document_identity(
            document.title
        )

        for reference in references:
            normalized_reference = (
                _normalize_document_identity(
                    reference
                )
            )

            if (
                title == normalized_reference
                or title.startswith(
                    normalized_reference + " "
                )
            ):
                matched.append(
                    document.id
                )
                break

    matched = list(
        dict.fromkeys(matched)
    )

    if not matched:
        return [], [
            (
                "Deterministic GIS evidence identified "
                "planning document(s), but no matching "
                "active PlanningDocument exists in the "
                "project. Document retrieval was blocked "
                "to avoid cross-jurisdiction evidence."
            )
        ]

    return matched, []

def _document_search_evidence(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    question: str,
    spatial_terms: list[str] | None = None,
    document_ids: list[uuid.UUID] | None = None,
) -> tuple[list[ToolEvidence], list[str]]:
    search_query = question.strip()

    if spatial_terms:
        search_query = (
            f"{search_query} "
            + " ".join(spatial_terms)
        )

    response = search_documents(
        session,
        owner=owner,
        project_id=project_id,
        request=DocumentSearchRequest(
            query=search_query,
            top_k=10,
            candidate_limit=50,
            document_ids=document_ids,
        ),
    )

    evidence: list[ToolEvidence] = []

    for hit in response.hits:
        provenance = hit.provenance

        evidence.append(
            ToolEvidence(
                project_id=project_id,
                site_id=site_id,
                tool_name="documents.search",
                deterministic=True,
                status="retrieved",
                payload={
                    "rank": hit.rank,
                    "text": hit.text,
                    "citation_label": (
                        hit.citation_label
                    ),
                    "document_title": (
                        provenance.document_title
                    ),
                    "document_class": (
                        provenance.document_class
                    ),
                    "authority": (
                        provenance.authority
                    ),
                    "page_number": (
                        provenance.page_number
                    ),
                    "chunk_index": (
                        provenance.chunk_index
                    ),
                    "chunk_sequence": (
                        provenance.chunk_sequence
                    ),
                    "version_sequence": (
                        provenance.version_sequence
                    ),
                    "version_label": (
                        provenance.version_label
                    ),
                    "publication_year": (
                        provenance.publication_year
                    ),
                    "keyword_rank": (
                        hit.keyword_rank
                    ),
                    "vector_rank": (
                        hit.vector_rank
                    ),
                    "keyword_score": (
                        hit.keyword_score
                    ),
                    "cosine_similarity": (
                        hit.cosine_similarity
                    ),
                    "fused_score": (
                        hit.fused_score
                    ),
                    "citation": (
                        hit.citation.model_dump(
                            mode="json",
                        )
                    ),
                    "search_query": (
                        search_query
                    ),
                },
                sources=[
                    EvidenceSourceRef(
                        kind="document_chunk",
                        id=(
                            provenance
                            .document_chunk_id
                        ),
                        hash=(
                            provenance
                            .chunk_text_sha256
                        ),
                    )
                ],
                limitations=[],
            )
        )

    return (
        evidence,
        list(response.limitations),
    )


def execute_planning_run(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    run_id: uuid.UUID,
    site_state: SiteState = SiteState.ACTIVE,
):
    run = get_planning_run(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
        run_id=run_id,
        site_state=site_state,
    )

    route = route_question(run.question)
    state = route.state
    tools = list(route.tools)

    if state == "clarification_required":
        return save_run_state(
            session,
            run,
            status=state,
            plan=tools,
            limitations=list(route.limitations),
        )

    if state == "evidence_required":
        requirements = ", ".join(route.required_evidence)
        return save_run_state(
            session,
            run,
            status="degraded",
            plan=tools,
            evidence=[],
            limitations=[
                *route.limitations,
                "Required evidence before deterministic execution: "
                f"{requirements}.",
            ],
        )

    evidence: list[ToolEvidence] = []
    tool_limitations: list[str] = []

    if "gis.site_area" in tools:
        evidence.append(
            execute_site_area(
                session,
                owner=owner,
                project_id=project_id,
                site_id=site_id,
                site_state=site_state,
            )
        )

    if "context.site_surroundings" in tools:
        (
            context_evidence,
            context_limitations,
        ) = execute_site_context(
            session,
            owner=owner,
            project_id=project_id,
            site_id=site_id,
            site_state=site_state,
        )

        evidence.extend(context_evidence)
        tool_limitations.extend(context_limitations)

    if "terrain.site_summary" in tools:
        try:
            evidence.append(
                execute_site_terrain_summary(
                    session,
                    owner=owner,
                    project_id=project_id,
                    site_id=site_id,
                )
            )
        except TerrainEvidenceMissing as exc:
            return save_run_state(
                session,
                run,
                status="degraded",
                plan=tools,
                evidence=[],
                limitations=[
                    *route.limitations,
                    str(exc),
                    "Required evidence before deterministic execution: "
                    + ", ".join(route.required_evidence)
                    + ".",
                ],
            )

    if "satellite.temporal_ndvi" in tools:
        temporal_evidence = execute_latest_temporal_ndvi(
            session,
            owner=owner,
            project_id=project_id,
            site_id=site_id,
            exclude_run_id=run.id,
        )

        if temporal_evidence is None:
            return save_run_state(
                session,
                run,
                status="degraded",
                plan=tools,
                evidence=evidence,
                limitations=[
                    *route.limitations,
                    "No persisted validated temporal measurement is available "
                    "for the active project/site. Run the approved T1/T2 "
                    "temporal analysis first.",
                ],
            )

        evidence.append(temporal_evidence)

    spatial_evidence: list[
        ToolEvidence
    ] = []

    if "gis.site_applicability" in tools:
        (
            spatial_evidence,
            spatial_limitations,
        ) = execute_site_applicability(
            session,
            owner=owner,
            project_id=project_id,
            site_id=site_id,
            site_state=site_state,
        )

        evidence.extend(
            spatial_evidence
        )
        tool_limitations.extend(
            spatial_limitations
        )

    spatial_terms = (
        _spatial_search_terms(
            spatial_evidence
        )
    )

    if "documents.search" in tools:
        # AUTO_RESEARCH_QUESTION_ROUTER_V1
        auto_research = auto_research_planning_documents(
            session,
            owner=owner,
            project_id=project_id,
            question=run.question,
        )
        tool_limitations.extend(auto_research.limitations)
        # AUTO_RESEARCH_EVIDENCE_BRIDGE_V1
        auto_research_document_ids = list(auto_research.document_ids)
        applicable_document_ids = None

        if spatial_evidence:
            (
                resolved_document_ids,
                applicability_limitations,
            ) = _applicable_document_ids(
                session,
                project_id=project_id,
                spatial_evidence=spatial_evidence,
            )

            tool_limitations.extend(
                applicability_limitations
            )

            if resolved_document_ids:
                applicable_document_ids = list(
                    dict.fromkeys(
                        [
                            *resolved_document_ids,
                            *auto_research_document_ids,
                        ]
                    )
                )
            elif auto_research_document_ids:
                # Research candidates may be searched, but this does not prove
                # that the document is legally/site-spatially applicable.
                applicable_document_ids = list(
                    auto_research_document_ids
                )
            else:
                applicable_document_ids = []

        else:
            # AUTO_RESEARCH_EVIDENCE_SCOPE_BRIDGE_V2
            # A document/policy question with no deterministic spatial
            # applicability evidence must not fall back to an unrestricted
            # project-wide document search. Restrict retrieval to the
            # documents selected/acquired by Auto Research for this question.
            applicable_document_ids = list(auto_research_document_ids)

        if (
            applicable_document_ids is None
            or applicable_document_ids
        ):
            (
                document_evidence,
                document_limitations,
            ) = _document_search_evidence(
                session,
                owner=owner,
                project_id=project_id,
                site_id=site_id,
                question=run.question,
                spatial_terms=spatial_terms,
                document_ids=(
                    applicable_document_ids
                ),
            )

            evidence.extend(
                document_evidence
            )
            tool_limitations.extend(
                document_limitations
            )

    if not evidence:
        return save_run_state(
            session,
            run,
            status="degraded",
            plan=tools,
            evidence=[],
            limitations=[
                *tool_limitations,
                (
                    "No approved tool "
                    "produced evidence for "
                    "this question."
                ),
            ],
        )

    instructions = (
        "You are GeoPilot AI Planning Officer. "
        "Explain only the supplied validated evidence. "
        "Do not invent numbers, citations, policy "
        "applicability, statutory compliance, or approval. "
        "Clearly separate evidence from advisory "
        "interpretation. "
        "When document evidence is supplied, preserve "
        "its page and citation identity when referring "
        "to factual claims. "
        "When gis.site_applicability evidence is "
        "supplied, treat its intersecting feature "
        "properties and overlap measurements as the "
        "only validated spatial basis for determining "
        "which planning block, zoning, land-use, or "
        "subzone intersects the active Site. "
        "Do not infer spatial applicability from a "
        "document name, a place name, or general "
        "knowledge when deterministic GIS evidence "
        "does not establish it. "
        "If no spatial applicability evidence exists, "
        "say that site-specific applicability cannot "
        "yet be confirmed. "
        "Do not calculate or derive new numeric values "
        "such as complements, differences, totals, or "
        "remaining percentages. You may only quote "
        "numeric evidence already supplied, with ordinary "
        "decimal rounding. "
        "When terrain.site_summary evidence is supplied, "
        "treat its elevation and slope values as the only "
        "validated terrain measurements for the active Site. "
        "Do not infer terrain values from NDVI or basemap context. "
        "When satellite.temporal_ndvi evidence is supplied, answer temporal "
        "or T1/T2 questions directly from that persisted measurement. "
        "You may describe the supplied before/after acquisition identity, "
        "mean NDVI values, changed pixel count, valid pixel count, changed "
        "percentage, usable coverage, and threshold policy when present. "
        "Do not claim that NDVI change proves construction, development, "
        "deforestation, flooding, land-use conversion, causation, illegality, "
        "or statutory non-compliance. "
        "When context.site_surroundings evidence is supplied, "
        "treat it only as provider-sourced contextual evidence about "
        "nearby or intersecting features around the active Site. "
        "You may report supplied names, categories, subtypes, spatial "
        "relations, and distances. Do not treat OpenStreetMap context "
        "as statutory zoning, legal parcel evidence, planning-policy "
        "authority, development approval, or proof of compliance. "
        "Do not claim absence of a feature merely because it was not "
        "returned or selected by the provider. "
        "For zoning, land-use, planning-block, or BPK "
        "questions, deterministic gis.site_applicability "
        "evidence has priority over retrieved document "
        "excerpts. Retrieved excerpts must not override "
        "the measured site classification."
    )

    prompt = (
        f"Question: {run.question}\n"
        f"Validated evidence: "
        f"{evidence_context(evidence)}"
    )

    settings = get_settings()

    providers = [
        OpenAIPlanningProvider(settings),
        OllamaPlanningProvider(settings),
    ]

    errors: list[str] = []

    for provider in providers:
        try:
            result = provider.generate(
                instructions=instructions,
                input_text=prompt,
            )

            synthesis = validate_synthesis(
                result.text,
                evidence,
            )

            _validate_spatial_classification_answer(
                run.question,
                synthesis,
                evidence,
            )

            return save_run_state(
                session,
                run,
                status="completed",
                plan=tools,
                evidence=[
                    item.model_dump(
                        mode="json"
                    )
                    for item in evidence
                ],
                provider_metadata={
                    "provider": (
                        result.provider
                    ),
                    "model": result.model,
                },
                synthesis=synthesis,
                limitations=[
                    *tool_limitations,
                    *sum(
                        (
                            item.limitations
                            for item in evidence
                        ),
                        [],
                    ),
                ],
            )

        except (
            AIProviderError,
            GroundingError,
        ) as exc:
            errors.append(
                str(exc)
            )

    return save_run_state(
        session,
        run,
        status="degraded",
        plan=tools,
        evidence=[
            item.model_dump(
                mode="json"
            )
            for item in evidence
        ],
        limitations=[
            *tool_limitations,
            *sum(
                (
                    item.limitations
                    for item in evidence
                ),
                [],
            ),
            (
                "AI synthesis unavailable; "
                "deterministic or retrieved "
                "evidence remains available."
            ),
            *errors,
        ],
    )
