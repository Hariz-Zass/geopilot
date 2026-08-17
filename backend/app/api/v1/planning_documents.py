from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.planning_document import (
    DocumentChunkBuildRequest,
    DocumentChunkBuildResponse,
    DocumentChunkResponse,
    DocumentEmbeddingIndexBuildRequest,
    DocumentEmbeddingIndexBuildResponse,
    DocumentEmbeddingIndexResponse,
    DocumentPageResponse,
    DocumentVersionCreateRequest,
    DocumentVersionResponse,
    PdfIngestionResponse,
    PlanningDocumentCreateRequest,
    PlanningDocumentResponse,
    PlanningDocumentUpdateRequest,
)
from app.services.document_chunking import (
    DocumentChunkingConfigError,
    DocumentChunkingStateError,
    build_document_chunks,
    list_document_chunks,
)
from app.services.document_indexing import (
    DocumentIndexingProviderError,
    DocumentIndexingStateError,
    build_document_embedding_index,
    list_document_embedding_indexes,
)
from app.services.pdf_ingestion import (
    PdfAlreadyIngestedError,
    PdfChecksumMismatchError,
    PdfTooLargeError,
    PdfTypeError,
    ingest_registered_pdf,
    list_document_pages,
)
from app.services.planning_documents import (
    DocumentVersionConflictError,
    DocumentVersionNotFoundError,
    PlanningDocumentNotFoundError,
    PlanningDocumentProjectNotFoundError,
    PlanningDocumentStateError,
    create_document_version,
    create_planning_document,
    get_document_version,
    get_planning_document,
    list_document_versions,
    list_planning_documents,
    update_planning_document,
)

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["planning-documents"])


def _translate(exc: Exception) -> AppError:
    if isinstance(exc, PlanningDocumentProjectNotFoundError):
        return AppError(code="project_not_found", message="Project not found.", status_code=404)
    if isinstance(exc, PlanningDocumentNotFoundError):
        return AppError(code="planning_document_not_found", message="Planning document not found.", status_code=404)
    if isinstance(exc, DocumentVersionNotFoundError):
        return AppError(code="document_version_not_found", message="Document version not found.", status_code=404)
    if isinstance(exc, DocumentVersionConflictError):
        return AppError(code="document_version_conflict", message=str(exc), status_code=409)
    return AppError(code="planning_document_state_invalid", message=str(exc) or "Planning document state is invalid.", status_code=409)


def _translate_pdf(exc: Exception) -> AppError:
    if isinstance(exc, PdfChecksumMismatchError):
        return AppError(code="pdf_checksum_mismatch", message=str(exc), status_code=409)
    if isinstance(exc, PdfAlreadyIngestedError):
        return AppError(code="pdf_already_ingested", message=str(exc), status_code=409)
    if isinstance(exc, PdfTooLargeError):
        return AppError(code="pdf_too_large", message=str(exc), status_code=413)
    if isinstance(exc, PdfTypeError):
        return AppError(code="invalid_pdf", message=str(exc), status_code=422)
    return _translate(exc)


@router.post("", response_model=PlanningDocumentResponse, status_code=201)
def create(
    project_id: uuid.UUID,
    payload: PlanningDocumentCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        document, _ = create_planning_document(session, owner=current_user, project_id=project_id, request=payload)
    except (PlanningDocumentProjectNotFoundError, PlanningDocumentStateError, DocumentVersionConflictError) as exc:
        raise _translate(exc) from exc
    return PlanningDocumentResponse.model_validate(document)


@router.get("", response_model=list[PlanningDocumentResponse])
def list_owned(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    include_archived: Annotated[bool, Query()] = False,
):
    try:
        documents = list_planning_documents(session, owner=current_user, project_id=project_id, include_archived=include_archived)
    except PlanningDocumentProjectNotFoundError as exc:
        raise _translate(exc) from exc
    return [PlanningDocumentResponse.model_validate(x) for x in documents]


@router.get("/{document_id}", response_model=PlanningDocumentResponse)
def get_one(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        document = get_planning_document(session, owner=current_user, project_id=project_id, document_id=document_id)
    except (PlanningDocumentProjectNotFoundError, PlanningDocumentNotFoundError) as exc:
        raise _translate(exc) from exc
    return PlanningDocumentResponse.model_validate(document)


@router.patch("/{document_id}", response_model=PlanningDocumentResponse)
def update(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: PlanningDocumentUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        document = update_planning_document(session, owner=current_user, project_id=project_id, document_id=document_id, request=payload)
    except (PlanningDocumentProjectNotFoundError, PlanningDocumentNotFoundError) as exc:
        raise _translate(exc) from exc
    return PlanningDocumentResponse.model_validate(document)


@router.post("/{document_id}/versions", response_model=DocumentVersionResponse, status_code=201)
def create_version(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: DocumentVersionCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        version = create_document_version(session, owner=current_user, project_id=project_id, document_id=document_id, request=payload)
    except (PlanningDocumentProjectNotFoundError, PlanningDocumentNotFoundError, PlanningDocumentStateError, DocumentVersionConflictError) as exc:
        raise _translate(exc) from exc
    return DocumentVersionResponse.model_validate(version)


@router.get("/{document_id}/versions", response_model=list[DocumentVersionResponse])
def list_versions(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        versions = list_document_versions(session, owner=current_user, project_id=project_id, document_id=document_id)
    except (PlanningDocumentProjectNotFoundError, PlanningDocumentNotFoundError) as exc:
        raise _translate(exc) from exc
    return [DocumentVersionResponse.model_validate(x) for x in versions]


@router.get("/{document_id}/versions/{version_id}", response_model=DocumentVersionResponse)
def get_version(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        version = get_document_version(session, owner=current_user, project_id=project_id, document_id=document_id, version_id=version_id)
    except (PlanningDocumentProjectNotFoundError, PlanningDocumentNotFoundError, DocumentVersionNotFoundError) as exc:
        raise _translate(exc) from exc
    return DocumentVersionResponse.model_validate(version)


@router.post(
    "/{document_id}/versions/{version_id}/ingest-pdf",
    response_model=PdfIngestionResponse,
)
async def ingest_pdf(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="Immutable PDF source bytes")],
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    from app.core.config import get_settings

    max_bytes = get_settings().document_upload_max_bytes
    data = await file.read(max_bytes + 1)
    try:
        result = ingest_registered_pdf(
            session,
            owner=current_user,
            project_id=project_id,
            document_id=document_id,
            version_id=version_id,
            filename=file.filename or "upload.pdf",
            content_type=file.content_type,
            data=data,
        )
    except (
        PlanningDocumentProjectNotFoundError,
        PlanningDocumentNotFoundError,
        DocumentVersionNotFoundError,
        PlanningDocumentStateError,
        PdfChecksumMismatchError,
        PdfAlreadyIngestedError,
        PdfTooLargeError,
        PdfTypeError,
    ) as exc:
        raise _translate_pdf(exc) from exc
    return PdfIngestionResponse(
        version=DocumentVersionResponse.model_validate(result.version),
        page_count=result.page_count,
        text_page_count=result.text_page_count,
        requires_ocr_page_count=result.requires_ocr_page_count,
        extraction_state=result.version.extraction_state,
        review_state=result.version.review_state,
    )


@router.get(
    "/{document_id}/versions/{version_id}/pages",
    response_model=list[DocumentPageResponse],
)
def get_pages(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        pages = list_document_pages(
            session,
            owner=current_user,
            project_id=project_id,
            document_id=document_id,
            version_id=version_id,
        )
    except (
        PlanningDocumentProjectNotFoundError,
        PlanningDocumentNotFoundError,
        DocumentVersionNotFoundError,
        PlanningDocumentStateError,
    ) as exc:
        raise _translate(exc) from exc
    return [DocumentPageResponse.model_validate(page) for page in pages]


@router.post(
    "/{document_id}/versions/{version_id}/chunks/build",
    response_model=DocumentChunkBuildResponse,
)
def build_chunks(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: DocumentChunkBuildRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        result = build_document_chunks(
            session,
            owner=current_user,
            project_id=project_id,
            document_id=document_id,
            version_id=version_id,
            max_chars=payload.max_chars,
            overlap_chars=payload.overlap_chars,
        )
    except DocumentChunkingConfigError as exc:
        raise AppError(code="document_chunking_config_invalid", message=str(exc), status_code=422) from exc
    except DocumentChunkingStateError as exc:
        raise AppError(code="document_chunking_state_invalid", message=str(exc), status_code=409) from exc
    except (
        PlanningDocumentProjectNotFoundError,
        PlanningDocumentNotFoundError,
        DocumentVersionNotFoundError,
        PlanningDocumentStateError,
    ) as exc:
        raise _translate(exc) from exc
    return DocumentChunkBuildResponse(
        version=DocumentVersionResponse.model_validate(result.version),
        chunk_count=result.chunk_count,
        chunked_page_count=result.chunked_page_count,
        skipped_page_count=result.skipped_page_count,
        max_chars=result.max_chars,
        overlap_chars=result.overlap_chars,
        chunker_version=result.chunker_version,
    )


@router.get(
    "/{document_id}/versions/{version_id}/chunks",
    response_model=list[DocumentChunkResponse],
)
def get_chunks(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    page_number: Annotated[int | None, Query(ge=1)] = None,
):
    try:
        chunks = list_document_chunks(
            session,
            owner=current_user,
            project_id=project_id,
            document_id=document_id,
            version_id=version_id,
            page_number=page_number,
        )
    except (
        PlanningDocumentProjectNotFoundError,
        PlanningDocumentNotFoundError,
        DocumentVersionNotFoundError,
        PlanningDocumentStateError,
    ) as exc:
        raise _translate(exc) from exc
    return [DocumentChunkResponse.model_validate(chunk) for chunk in chunks]


@router.post(
    "/{document_id}/versions/{version_id}/chunks/index",
    response_model=DocumentEmbeddingIndexBuildResponse,
)
def build_embedding_index(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: DocumentEmbeddingIndexBuildRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        index = build_document_embedding_index(
            session, owner=current_user, project_id=project_id, document_id=document_id,
            version_id=version_id, force_rebuild=payload.force_rebuild,
        )
        version = get_document_version(session, owner=current_user, project_id=project_id, document_id=document_id, version_id=version_id)
    except (PlanningDocumentProjectNotFoundError, PlanningDocumentNotFoundError, DocumentVersionNotFoundError) as exc:
        raise _translate(exc) from exc
    except DocumentIndexingStateError as exc:
        raise AppError(code="document_indexing_state_invalid", message=str(exc), status_code=409) from exc
    except DocumentIndexingProviderError as exc:
        raise AppError(code="embedding_provider_failed", message=str(exc), status_code=503) from exc
    return DocumentEmbeddingIndexBuildResponse(
        version=DocumentVersionResponse.model_validate(version),
        index=DocumentEmbeddingIndexResponse.model_validate(index),
    )


@router.get(
    "/{document_id}/versions/{version_id}/embedding-indexes",
    response_model=list[DocumentEmbeddingIndexResponse],
)
def get_embedding_indexes(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        indexes = list_document_embedding_indexes(
            session, owner=current_user, project_id=project_id, document_id=document_id, version_id=version_id
        )
    except (PlanningDocumentProjectNotFoundError, PlanningDocumentNotFoundError, DocumentVersionNotFoundError) as exc:
        raise _translate(exc) from exc
    return [DocumentEmbeddingIndexResponse.model_validate(item) for item in indexes]
