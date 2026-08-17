from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.planning_document import DocumentVersion, PlanningDocument
from app.models.user import User
from app.schemas.planning_document import (
    DocumentVersionCreateRequest,
    PlanningDocumentCreateRequest,
    PlanningDocumentUpdateRequest,
)
from app.services.isolation import ProjectScopeNotFoundError, ProjectState, ScopeStateError, resolve_project_scope


class PlanningDocumentNotFoundError(Exception): pass
class PlanningDocumentProjectNotFoundError(Exception): pass
class PlanningDocumentStateError(Exception): pass
class DocumentVersionNotFoundError(Exception): pass
class DocumentVersionConflictError(Exception): pass


def _project(session: Session, *, owner: User, project_id: uuid.UUID, active: bool = False):
    try:
        return resolve_project_scope(
            session,
            owner=owner,
            project_id=project_id,
            state=ProjectState.ACTIVE if active else ProjectState.ANY,
        ).project
    except ProjectScopeNotFoundError as exc:
        raise PlanningDocumentProjectNotFoundError from exc
    except ScopeStateError as exc:
        raise PlanningDocumentStateError(str(exc)) from exc


def _get_document(session: Session, *, owner: User, project_id: uuid.UUID, document_id: uuid.UUID) -> PlanningDocument:
    project = _project(session, owner=owner, project_id=project_id)
    document = session.scalar(
        select(PlanningDocument).where(
            PlanningDocument.id == document_id,
            PlanningDocument.project_id == project.id,
        )
    )
    if document is None:
        raise PlanningDocumentNotFoundError
    return document


def _next_sequence(session: Session, document_id: uuid.UUID) -> int:
    current = session.scalar(
        select(func.max(DocumentVersion.version_sequence)).where(DocumentVersion.document_id == document_id)
    )
    return int(current or 0) + 1


def _version_kwargs(request: DocumentVersionCreateRequest) -> dict:
    return request.model_dump()


def create_planning_document(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    request: PlanningDocumentCreateRequest,
) -> tuple[PlanningDocument, DocumentVersion]:
    project = _project(session, owner=owner, project_id=project_id, active=True)
    document_data = request.model_dump(exclude={"initial_version"})
    document = PlanningDocument(project_id=project.id, **document_data)
    session.add(document)
    session.flush()
    version = DocumentVersion(
        document_id=document.id,
        version_sequence=1,
        **_version_kwargs(request.initial_version),
    )
    session.add(version)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DocumentVersionConflictError("document version source already exists") from exc
    session.refresh(document)
    session.refresh(version)
    return document, version


def list_planning_documents(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    include_archived: bool = False,
) -> list[PlanningDocument]:
    project = _project(session, owner=owner, project_id=project_id)
    stmt = select(PlanningDocument).where(PlanningDocument.project_id == project.id)
    if not include_archived:
        stmt = stmt.where(PlanningDocument.is_archived.is_(False))
    return list(session.scalars(stmt.order_by(PlanningDocument.created_at.desc(), PlanningDocument.id.desc())))


def get_planning_document(session: Session, *, owner: User, project_id: uuid.UUID, document_id: uuid.UUID) -> PlanningDocument:
    return _get_document(session, owner=owner, project_id=project_id, document_id=document_id)


def update_planning_document(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    request: PlanningDocumentUpdateRequest,
) -> PlanningDocument:
    document = _get_document(session, owner=owner, project_id=project_id, document_id=document_id)
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(document, key, value)
    session.commit()
    session.refresh(document)
    return document


def create_document_version(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    request: DocumentVersionCreateRequest,
) -> DocumentVersion:
    document = _get_document(session, owner=owner, project_id=project_id, document_id=document_id)
    _project(session, owner=owner, project_id=project_id, active=True)
    if document.is_archived:
        raise PlanningDocumentStateError("archived planning document cannot receive new versions")
    version = DocumentVersion(
        document_id=document.id,
        version_sequence=_next_sequence(session, document.id),
        **_version_kwargs(request),
    )
    session.add(version)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DocumentVersionConflictError("duplicate document version checksum or sequence") from exc
    session.refresh(version)
    return version


def list_document_versions(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
) -> list[DocumentVersion]:
    document = _get_document(session, owner=owner, project_id=project_id, document_id=document_id)
    return list(session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_sequence.asc())
    ))


def get_document_version(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> DocumentVersion:
    document = _get_document(session, owner=owner, project_id=project_id, document_id=document_id)
    version = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document.id,
        )
    )
    if version is None:
        raise DocumentVersionNotFoundError
    return version
