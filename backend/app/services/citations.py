from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.planning_document import DocumentChunk, DocumentPage, DocumentVersion, PlanningDocument
from app.models.user import User
from app.schemas.citations import DocumentCitationReference, ResolvedDocumentCitation
from app.services.isolation import ProjectScopeNotFoundError, ProjectState, ScopeStateError, resolve_project_scope


class CitationProjectNotFoundError(Exception):
    pass


class CitationSourceNotFoundError(Exception):
    pass


class CitationSourceUnavailableError(Exception):
    pass


class CitationReferenceStaleError(Exception):
    pass


def build_citation_reference(
    *,
    project_id: uuid.UUID,
    document: PlanningDocument,
    version: DocumentVersion,
    page: DocumentPage,
    chunk: DocumentChunk,
) -> DocumentCitationReference:
    return DocumentCitationReference(
        project_id=project_id,
        document_id=document.id,
        document_version_id=version.id,
        document_page_id=page.id,
        document_chunk_id=chunk.id,
        page_number=page.page_number,
        version_checksum_sha256=version.checksum_sha256,
        page_text_sha256=page.text_sha256,
        chunk_text_sha256=chunk.text_sha256,
    )


def _citation_label(document: PlanningDocument, version: DocumentVersion, page: DocumentPage) -> str:
    source = document.title.strip()
    version_part = f", {version.version_label.strip()}" if version.version_label and version.version_label.strip() else ""
    return f"{source}{version_part}, p. {page.page_number}"


def _resolve_one(
    session: Session,
    *,
    project_id: uuid.UUID,
    reference: DocumentCitationReference,
) -> ResolvedDocumentCitation:
    if reference.project_id != project_id:
        raise CitationSourceNotFoundError("Citation reference does not belong to the requested project.")

    row = session.execute(
        select(PlanningDocument, DocumentVersion, DocumentPage, DocumentChunk)
        .join(DocumentVersion, DocumentVersion.document_id == PlanningDocument.id)
        .join(DocumentPage, DocumentPage.document_version_id == DocumentVersion.id)
        .join(DocumentChunk, DocumentChunk.document_page_id == DocumentPage.id)
        .where(
            PlanningDocument.project_id == project_id,
            PlanningDocument.id == reference.document_id,
            DocumentVersion.id == reference.document_version_id,
            DocumentPage.id == reference.document_page_id,
            DocumentChunk.id == reference.document_chunk_id,
        )
    ).one_or_none()
    if row is None:
        raise CitationSourceNotFoundError("Citation source could not be resolved in the requested project.")

    document, version, page, chunk = row
    if document.is_archived:
        raise CitationSourceUnavailableError("Citation source document is archived.")
    if version.extraction_state not in {"ready", "requires_review"}:
        raise CitationSourceUnavailableError("Citation source version is not in an evidence-readable extraction state.")
    if page.extraction_state != "ready" or page.requires_ocr:
        raise CitationSourceUnavailableError("Citation source page is not validated text evidence and requires review/OCR.")

    stale = (
        reference.page_number != page.page_number
        or reference.version_checksum_sha256 != version.checksum_sha256
        or reference.page_text_sha256 != page.text_sha256
        or reference.chunk_text_sha256 != chunk.text_sha256
        or chunk.document_version_id != version.id
        or chunk.page_number != page.page_number
    )
    if stale:
        raise CitationReferenceStaleError("Citation reference no longer matches the current persisted source lineage.")

    actual_page_hash = hashlib.sha256(page.extracted_text.encode("utf-8")).hexdigest()
    actual_chunk_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
    if actual_page_hash != page.text_sha256 or actual_chunk_hash != chunk.text_sha256:
        raise CitationReferenceStaleError("Persisted citation text does not match its recorded SHA-256 identity.")

    # Revalidate that the persisted chunk still represents the exact recorded page substring.
    if chunk.start_char < 0 or chunk.end_char > len(page.extracted_text) or chunk.start_char >= chunk.end_char:
        raise CitationReferenceStaleError("Persisted citation character offsets are invalid.")
    if page.extracted_text[chunk.start_char:chunk.end_char] != chunk.text:
        raise CitationReferenceStaleError("Persisted chunk text no longer matches its page source range.")

    limitations: list[str] = []
    if version.review_state != "reviewed":
        limitations.append(f"Document version review_state is '{version.review_state}'; citation proves source provenance, not planning applicability.")
    if version.extraction_state == "requires_review":
        limitations.append("Document version extraction requires review; this cited page itself passed text extraction validation.")

    return ResolvedDocumentCitation(
        reference=reference,
        citation_label=_citation_label(document, version, page),
        document_title=document.title,
        document_class=document.document_class,
        authority=document.authority,
        jurisdiction=document.jurisdiction,
        geographic_applicability=document.geographic_applicability,
        version_sequence=version.version_sequence,
        version_label=version.version_label,
        publication_year=version.publication_year,
        publication_date=version.publication_date.isoformat() if version.publication_date else None,
        page_number=page.page_number,
        chunk_index=chunk.chunk_index,
        chunk_sequence=chunk.chunk_sequence,
        start_char=chunk.start_char,
        end_char=chunk.end_char,
        text=chunk.text,
        review_state=version.review_state,
        limitations=limitations,
    )


def resolve_citations(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    references: list[DocumentCitationReference],
) -> list[ResolvedDocumentCitation]:
    try:
        resolve_project_scope(session, owner=owner, project_id=project_id, state=ProjectState.ACTIVE)
    except ProjectScopeNotFoundError as exc:
        raise CitationProjectNotFoundError from exc
    except ScopeStateError as exc:
        raise CitationSourceUnavailableError(str(exc)) from exc

    # Duplicate identities are ambiguous/redundant evidence and are rejected rather than silently de-duplicated.
    identities = [ref.document_chunk_id for ref in references]
    if len(set(identities)) != len(identities):
        raise CitationSourceUnavailableError("Duplicate citation chunk identities are not allowed in one resolution request.")

    # All-or-nothing validation: no partial validated evidence envelope is returned.
    return [_resolve_one(session, project_id=project_id, reference=reference) for reference in references]
