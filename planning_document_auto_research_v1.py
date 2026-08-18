from __future__ import annotations

from dataclasses import dataclass, field
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.planning_document import DocumentVersion, PlanningDocument
from app.models.user import User
from app.services.planning_document_acquisition import (
    PlanMalaysiaOfficialProvider,
    PlanningDocumentAcquisitionError,
    acquire_candidate,
    ingest_acquired_document,
)

_STATE_ALIASES = {
    "johor": "Johor",
    "kedah": "Kedah",
    "kelantan": "Kelantan",
    "melaka": "Melaka",
    "malacca": "Melaka",
    "negeri sembilan": "Negeri Sembilan",
    "pahang": "Pahang",
    "perak": "Perak",
    "perlis": "Perlis",
    "pulau pinang": "Pulau Pinang",
    "penang": "Pulau Pinang",
    "sabah": "Sabah",
    "sarawak": "Sarawak",
    "selangor": "Selangor",
    "terengganu": "Terengganu",
    "kuala lumpur": "W.P. Kuala Lumpur",
    "putrajaya": "W.P. Putrajaya",
    "labuan": "W.P. Labuan",
}

_GPP_TERMS = (
    "gpp",
    "garis panduan",
    "guideline",
    "buffer",
    "setback",
    "anjakan",
    "parking",
    "tempat letak kereta",
    "kepadatan",
    "densiti",
    "density",
    "plot ratio",
    "nisbah plot",
    "open space",
    "kawasan lapang",
)

_RT_TERMS = (
    "rancangan tempatan",
    " rt ",
    "zoning",
    "zon guna tanah",
    "guna tanah",
    "land use",
    "kelas kegunaan",
    "intensiti",
    "kepadatan",
    "densiti",
    "density",
)

_RSN_TERMS = (
    "rancangan struktur",
    "rsn",
    "state policy",
    "state planning",
)

_RKK_TERMS = (
    "rancangan kawasan khas",
    "rkk",
    "kawasan khas",
    "special area plan",
)

_RFN_TERMS = (
    "rancangan fizikal negara",
    "rfn",
    "national physical plan",
)


@dataclass
class AutoResearchResult:
    requested_classes: list[str] = field(default_factory=list)
    existing_document_ids: list[uuid.UUID] = field(default_factory=list)
    acquired_document_ids: list[uuid.UUID] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    @property
    def document_ids(self) -> list[uuid.UUID]:
        return list(
            dict.fromkeys(
                [*self.existing_document_ids, *self.acquired_document_ids]
            )
        )


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    padded = f" {text.casefold()} "
    return any(term.casefold() in padded for term in terms)


def infer_document_classes(question: str) -> list[str]:
    q = question.casefold()
    classes: list[str] = []

    if _contains(q, _RKK_TERMS):
        classes.append("RKK")
    if _contains(q, _RT_TERMS):
        classes.append("RT")
    if _contains(q, _RSN_TERMS):
        classes.append("RSN")
    if _contains(q, _RFN_TERMS):
        classes.append("RFN")
    if _contains(q, _GPP_TERMS):
        classes.append("GPP")

    if not classes and _contains(
        q,
        (
            "policy",
            "polisi",
            "dasar",
            "planning document",
            "dokumen perancangan",
            "syarat pembangunan",
            "development control",
            "piawaian",
            "standard",
        ),
    ):
        classes.extend(["RT", "GPP"])

    return list(dict.fromkeys(classes))


def infer_jurisdiction(question: str) -> str | None:
    q = question.casefold()
    for alias in sorted(_STATE_ALIASES, key=len, reverse=True):
        if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", q):
            return _STATE_ALIASES[alias]
    return None


def _ready_documents(
    session: Session,
    *,
    project_id: uuid.UUID,
    document_class: str,
) -> list[uuid.UUID]:
    stmt = (
        select(PlanningDocument.id)
        .join(DocumentVersion, DocumentVersion.document_id == PlanningDocument.id)
        .where(
            PlanningDocument.project_id == project_id,
            PlanningDocument.document_class == document_class,
            PlanningDocument.is_archived.is_(False),
            DocumentVersion.ingestion_state == "available",
            DocumentVersion.index_state == "ready",
        )
        .order_by(
            PlanningDocument.created_at.desc(),
            PlanningDocument.id.desc(),
        )
    )
    return list(dict.fromkeys(session.scalars(stmt).all()))


def _existing_by_source_uri(
    session: Session,
    *,
    project_id: uuid.UUID,
    source_uri: str,
) -> uuid.UUID | None:
    return session.scalar(
        select(PlanningDocument.id)
        .join(DocumentVersion, DocumentVersion.document_id == PlanningDocument.id)
        .where(
            PlanningDocument.project_id == project_id,
            PlanningDocument.is_archived.is_(False),
            DocumentVersion.source_uri == source_uri,
            DocumentVersion.ingestion_state == "available",
            DocumentVersion.index_state == "ready",
        )
        .order_by(PlanningDocument.created_at.desc())
    )


def _existing_by_checksum(
    session: Session,
    *,
    project_id: uuid.UUID,
    checksum: str,
) -> uuid.UUID | None:
    return session.scalar(
        select(PlanningDocument.id)
        .join(DocumentVersion, DocumentVersion.document_id == PlanningDocument.id)
        .where(
            PlanningDocument.project_id == project_id,
            PlanningDocument.is_archived.is_(False),
            DocumentVersion.checksum_sha256 == checksum,
            DocumentVersion.ingestion_state == "available",
            DocumentVersion.index_state == "ready",
        )
        .order_by(PlanningDocument.created_at.desc())
    )


def auto_research_planning_documents(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    question: str,
    max_new_documents: int = 3,
    provider: PlanMalaysiaOfficialProvider | None = None,
) -> AutoResearchResult:
    """
    Evidence-first automatic planning-document acquisition.

    Discovery metadata is never promoted into a planning conclusion.
    Documents are searchable only after passing the existing immutable
    acquisition -> PDF ingestion -> extraction/OCR -> chunk -> index pipeline.
    """

    result = AutoResearchResult()
    result.requested_classes = infer_document_classes(question)
    if not result.requested_classes:
        return result

    jurisdiction = infer_jurisdiction(question)
    official = provider or PlanMalaysiaOfficialProvider()
    acquired_count = 0

    for document_class in result.requested_classes:
        ready = _ready_documents(
            session,
            project_id=project_id,
            document_class=document_class,
        )
        result.existing_document_ids.extend(ready)

        if document_class == "RFN":
            result.limitations.append(
                "RFN automatic acquisition remains fail-closed until an accepted official RFN catalogue adapter is available."
            )
            continue

        if document_class in {"RT", "RSN", "RKK"} and not jurisdiction:
            if ready:
                continue
            result.limitations.append(
                f"{document_class} automatic discovery was not attempted because the question did not identify a Malaysian state/jurisdiction."
            )
            continue

        if acquired_count >= max_new_documents:
            result.limitations.append(
                "Automatic planning-document acquisition reached the bounded per-question document limit."
            )
            break

        try:
            candidates = official.discover(
                document_class=document_class,
                jurisdiction=jurisdiction,
                query=question,
            )
        except PlanningDocumentAcquisitionError as exc:
            result.limitations.append(
                f"{document_class} official discovery failed safely: {exc}"
            )
            continue

        if not candidates:
            result.limitations.append(
                f"No matching official {document_class} catalogue candidate was found for this question."
            )
            continue

        # V1 intentionally accepts only the top provider-ranked official candidate.
        candidate = candidates[0]

        try:
            resolved = official.resolve_candidate_pdf_links(candidate)
        except PlanningDocumentAcquisitionError as exc:
            result.limitations.append(
                f"{document_class} official PDF resolution failed safely: {exc}"
            )
            continue

        if not resolved:
            result.limitations.append(
                f"{document_class} candidate did not resolve to an approved official PDF."
            )
            continue

        pdf_candidate = resolved[0]

        existing = _existing_by_source_uri(
            session,
            project_id=project_id,
            source_uri=pdf_candidate.source_uri,
        )
        if existing:
            result.existing_document_ids.append(existing)
            continue

        try:
            acquired = acquire_candidate(pdf_candidate)
        except PlanningDocumentAcquisitionError as exc:
            result.limitations.append(
                f"{document_class} official PDF acquisition failed safely: {exc}"
            )
            continue

        existing = _existing_by_checksum(
            session,
            project_id=project_id,
            checksum=acquired.checksum_sha256,
        )
        if existing:
            result.existing_document_ids.append(existing)
            continue

        pipeline = ingest_acquired_document(
            session,
            owner=owner,
            project_id=project_id,
            acquired=acquired,
            build_chunks=True,
            build_index=True,
        )
        result.acquired_document_ids.append(pipeline["document"].id)
        acquired_count += 1

    result.existing_document_ids = list(
        dict.fromkeys(result.existing_document_ids)
    )
    result.acquired_document_ids = list(
        dict.fromkeys(result.acquired_document_ids)
    )
    return result
