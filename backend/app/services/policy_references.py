from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.policy_reference import PolicyReference
from app.models.user import User
from app.schemas.citations import DocumentCitationReference, ResolvedDocumentCitation
from app.schemas.policy_reference import (
    PolicyReferenceCreateRequest,
    PolicyReferenceReviewRequest,
    PolicyReferenceUpdateRequest,
)
from app.services.citations import (
    CitationProjectNotFoundError,
    CitationReferenceStaleError,
    CitationSourceNotFoundError,
    CitationSourceUnavailableError,
    resolve_citations,
)
from app.services.isolation import ProjectScopeNotFoundError, ProjectState, ScopeStateError, resolve_project_scope


class PolicyReferenceProjectNotFoundError(Exception):
    pass


class PolicyReferenceNotFoundError(Exception):
    pass


class PolicyReferenceStateError(Exception):
    pass


class PolicyReferenceSourceError(Exception):
    pass


class PolicyReferenceSourceStaleError(Exception):
    pass


def _project(session: Session, *, owner: User, project_id: uuid.UUID, active: bool = False):
    try:
        return resolve_project_scope(
            session,
            owner=owner,
            project_id=project_id,
            state=ProjectState.ACTIVE if active else ProjectState.ANY,
        ).project
    except ProjectScopeNotFoundError as exc:
        raise PolicyReferenceProjectNotFoundError from exc
    except ScopeStateError as exc:
        raise PolicyReferenceStateError(str(exc)) from exc


def _get(session: Session, *, owner: User, project_id: uuid.UUID, policy_reference_id: uuid.UUID) -> PolicyReference:
    project = _project(session, owner=owner, project_id=project_id)
    item = session.scalar(
        select(PolicyReference).where(
            PolicyReference.id == policy_reference_id,
            PolicyReference.project_id == project.id,
        )
    )
    if item is None:
        raise PolicyReferenceNotFoundError
    return item


def _citation_from_model(item: PolicyReference) -> DocumentCitationReference:
    return DocumentCitationReference(
        project_id=item.project_id,
        document_id=item.document_id,
        document_version_id=item.document_version_id,
        document_page_id=item.document_page_id,
        document_chunk_id=item.document_chunk_id,
        page_number=item.page_number,
        version_checksum_sha256=item.version_checksum_sha256,
        page_text_sha256=item.page_text_sha256,
        chunk_text_sha256=item.chunk_text_sha256,
    )


def _resolve_source(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    reference: DocumentCitationReference,
) -> ResolvedDocumentCitation:
    try:
        return resolve_citations(
            session,
            owner=owner,
            project_id=project_id,
            references=[reference],
        )[0]
    except CitationReferenceStaleError as exc:
        raise PolicyReferenceSourceStaleError(str(exc)) from exc
    except (CitationProjectNotFoundError, CitationSourceNotFoundError) as exc:
        raise PolicyReferenceSourceError("Policy source citation could not be resolved.") from exc
    except CitationSourceUnavailableError as exc:
        raise PolicyReferenceSourceError(str(exc)) from exc


def _validate_snapshot(item: PolicyReference, source: ResolvedDocumentCitation) -> None:
    if (
        item.source_wording != source.text
        or item.document_class_snapshot != source.document_class
        or item.authority_snapshot != source.authority
        or item.page_number != source.page_number
    ):
        raise PolicyReferenceSourceStaleError(
            "PolicyReference source snapshot no longer matches the validated citation source."
        )


def create_policy_reference(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    request: PolicyReferenceCreateRequest,
) -> PolicyReference:
    _project(session, owner=owner, project_id=project_id, active=True)
    source = _resolve_source(session, owner=owner, project_id=project_id, reference=request.citation)
    ref = request.citation
    item = PolicyReference(
        project_id=project_id,
        document_id=ref.document_id,
        document_version_id=ref.document_version_id,
        document_page_id=ref.document_page_id,
        document_chunk_id=ref.document_chunk_id,
        created_by_user_id=owner.id,
        label=request.label.strip() if request.label and request.label.strip() else None,
        document_class_snapshot=source.document_class,
        authority_snapshot=source.authority,
        page_number=source.page_number,
        version_checksum_sha256=ref.version_checksum_sha256,
        page_text_sha256=ref.page_text_sha256,
        chunk_text_sha256=ref.chunk_text_sha256,
        source_wording=source.text,
        policy_statement=request.policy_statement.strip(),
        applicability_notes=request.applicability_notes,
        representation_state="draft",
        review_state="unreviewed",
        applicability_status="unassessed",
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def list_policy_references(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    include_archived: bool = False,
) -> list[PolicyReference]:
    project = _project(session, owner=owner, project_id=project_id)
    stmt = select(PolicyReference).where(PolicyReference.project_id == project.id)
    if not include_archived:
        stmt = stmt.where(PolicyReference.is_archived.is_(False))
    return list(session.scalars(stmt.order_by(PolicyReference.created_at.desc(), PolicyReference.id.desc())))


def get_policy_reference(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    policy_reference_id: uuid.UUID,
) -> PolicyReference:
    return _get(
        session,
        owner=owner,
        project_id=project_id,
        policy_reference_id=policy_reference_id,
    )


def update_policy_reference(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    policy_reference_id: uuid.UUID,
    request: PolicyReferenceUpdateRequest,
) -> PolicyReference:
    item = _get(session, owner=owner, project_id=project_id, policy_reference_id=policy_reference_id)
    _project(session, owner=owner, project_id=project_id, active=True)
    changes = request.model_dump(exclude_unset=True)

    if item.representation_state == "final":
        illegal = set(changes) - {"is_archived"}
        if illegal:
            raise PolicyReferenceStateError("Final PolicyReference content is immutable; only archive state may change.")

    if "policy_statement" in changes and changes["policy_statement"] is not None:
        changes["policy_statement"] = changes["policy_statement"].strip()
    if "label" in changes and changes["label"] is not None:
        changes["label"] = changes["label"].strip() or None

    for key, value in changes.items():
        setattr(item, key, value)
    session.commit()
    session.refresh(item)
    return item


def review_policy_reference(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    policy_reference_id: uuid.UUID,
    request: PolicyReferenceReviewRequest,
) -> PolicyReference:
    item = _get(session, owner=owner, project_id=project_id, policy_reference_id=policy_reference_id)
    _project(session, owner=owner, project_id=project_id, active=True)
    if item.is_archived:
        raise PolicyReferenceStateError("Archived PolicyReference cannot be reviewed.")
    if item.representation_state == "final":
        raise PolicyReferenceStateError("Final PolicyReference cannot be reviewed again.")

    if request.action == "verify":
        source = _resolve_source(session, owner=owner, project_id=project_id, reference=_citation_from_model(item))
        _validate_snapshot(item, source)
        item.representation_state = "final"
        item.review_state = "verified"
        item.reviewed_by_user_id = owner.id
        item.reviewed_at = datetime.now(timezone.utc)
    elif request.action == "reject":
        item.representation_state = "final"
        item.review_state = "rejected"
        item.reviewed_by_user_id = owner.id
        item.reviewed_at = datetime.now(timezone.utc)
    else:
        item.representation_state = "draft"
        item.review_state = "requires_review"
        item.reviewed_by_user_id = owner.id
        item.reviewed_at = datetime.now(timezone.utc)

    item.applicability_status = request.applicability_status
    item.applicability_notes = request.applicability_notes
    item.review_notes = request.review_notes
    session.commit()
    session.refresh(item)
    return item


def resolve_policy_reference_for_use(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    policy_reference_id: uuid.UUID,
) -> tuple[PolicyReference, ResolvedDocumentCitation, list[str]]:
    item = _get(session, owner=owner, project_id=project_id, policy_reference_id=policy_reference_id)
    _project(session, owner=owner, project_id=project_id, active=True)
    if item.is_archived:
        raise PolicyReferenceStateError("Archived PolicyReference is unavailable for evidence use.")
    if item.representation_state != "final" or item.review_state != "verified":
        raise PolicyReferenceStateError("Only final, verified PolicyReference records may be used as policy evidence.")

    source = _resolve_source(session, owner=owner, project_id=project_id, reference=_citation_from_model(item))
    _validate_snapshot(item, source)

    limitations = list(source.limitations)
    if item.applicability_status in {"unassessed", "requires_review"}:
        limitations.append(
            "PolicyReference is verified as a source-grounded interpretation, but site/material applicability is not confirmed."
        )
    elif item.applicability_status == "limited":
        limitations.append("PolicyReference applicability is explicitly limited; review applicability_notes before use.")
    limitations.append("PolicyReference verification is not statutory approval, legal certification, or planning permission.")
    return item, source, limitations
