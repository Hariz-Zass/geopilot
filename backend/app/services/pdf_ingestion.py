from __future__ import annotations

import hashlib
import io
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.planning_document import DocumentPage, DocumentVersion, PlanningDocument
from app.models.user import User
from app.services.planning_documents import (
    DocumentVersionNotFoundError,
    PlanningDocumentNotFoundError,
    PlanningDocumentProjectNotFoundError,
    PlanningDocumentStateError,
)
from app.services.isolation import ProjectScopeNotFoundError, ProjectState, ScopeStateError, resolve_project_scope


class PdfIngestionError(Exception):
    pass


class PdfChecksumMismatchError(PdfIngestionError):
    pass


class PdfTypeError(PdfIngestionError):
    pass


class PdfTooLargeError(PdfIngestionError):
    pass


class PdfAlreadyIngestedError(PdfIngestionError):
    pass


@dataclass(frozen=True)
class PdfIngestionSummary:
    version: DocumentVersion
    page_count: int
    text_page_count: int
    requires_ocr_page_count: int


def _resolve_version(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> tuple[PlanningDocument, DocumentVersion]:
    try:
        project = resolve_project_scope(
            session, owner=owner, project_id=project_id, state=ProjectState.ACTIVE
        ).project
    except ProjectScopeNotFoundError as exc:
        raise PlanningDocumentProjectNotFoundError from exc
    except ScopeStateError as exc:
        raise PlanningDocumentStateError(str(exc)) from exc

    document = session.scalar(
        select(PlanningDocument).where(
            PlanningDocument.id == document_id,
            PlanningDocument.project_id == project.id,
        )
    )
    if document is None:
        raise PlanningDocumentNotFoundError
    if document.is_archived:
        raise PlanningDocumentStateError("archived planning document cannot be ingested")

    version = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document.id,
        )
    )
    if version is None:
        raise DocumentVersionNotFoundError
    return document, version


def _storage_target(
    *, project_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID, checksum: str
) -> tuple[Path, str]:
    settings = get_settings()
    root = Path(settings.document_storage_root).expanduser().resolve()
    relative = Path(str(project_id)) / str(document_id) / str(version_id) / f"{checksum}.pdf"
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise PdfIngestionError("invalid document storage target")
    return target, f"local://documents/{relative.as_posix()}"


def _extract_pages(data: bytes) -> tuple[list[dict], bool]:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except (PdfReadError, ValueError, OSError, EOFError) as exc:
        raise PdfTypeError("uploaded file is not a readable PDF") from exc

    if reader.is_encrypted:
        try:
            decrypt_result = reader.decrypt("")
        except Exception:
            decrypt_result = 0
        if not decrypt_result:
            return [], True

    pages: list[dict] = []
    try:
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
                state = "ready" if text.strip() else "empty"
                requires_ocr = state == "empty"
                method = "pypdf_text" if state == "ready" else "none"
            except Exception:
                text = ""
                state = "failed"
                requires_ocr = True
                method = "none"
            pages.append(
                {
                    "page_number": index,
                    "extracted_text": text,
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "char_count": len(text),
                    "extraction_method": method,
                    "extraction_state": state,
                    "requires_ocr": requires_ocr,
                }
            )
    except Exception as exc:
        raise PdfTypeError("PDF page structure could not be read safely") from exc

    if not pages:
        raise PdfTypeError("PDF contains no readable pages")
    return pages, False


def ingest_registered_pdf(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> PdfIngestionSummary:
    document, version = _resolve_version(
        session,
        owner=owner,
        project_id=project_id,
        document_id=document_id,
        version_id=version_id,
    )
    settings = get_settings()
    if len(data) > settings.document_upload_max_bytes:
        raise PdfTooLargeError(f"PDF exceeds {settings.document_upload_max_bytes} byte upload limit")
    if len(data) < 5 or not data.startswith(b"%PDF-"):
        raise PdfTypeError("uploaded file does not have a PDF signature")
    if content_type and content_type.lower() not in {"application/pdf", "application/octet-stream"}:
        raise PdfTypeError("uploaded content type is not PDF")
    if version.source_kind != "upload":
        raise PlanningDocumentStateError("manual PDF upload is only valid for upload source versions")
    if version.ingestion_state == "available" or version.storage_uri:
        raise PdfAlreadyIngestedError("document version already has an ingested source artifact")

    actual_checksum = hashlib.sha256(data).hexdigest()
    if actual_checksum != version.checksum_sha256:
        raise PdfChecksumMismatchError("uploaded bytes do not match immutable version checksum")
    if version.file_size_bytes is not None and version.file_size_bytes != len(data):
        raise PdfChecksumMismatchError("uploaded byte size does not match immutable version metadata")

    page_rows, encrypted_requires_review = _extract_pages(data)
    target, storage_uri = _storage_target(
        project_id=project_id,
        document_id=document.id,
        version_id=version.id,
        checksum=actual_checksum,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_suffix(".pdf.tmp")
    try:
        with open(temp_target, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_target, target)

        session.execute(delete(DocumentPage).where(DocumentPage.document_version_id == version.id))
        for page_data in page_rows:
            session.add(DocumentPage(document_version_id=version.id, **page_data))

        requires_review = encrypted_requires_review or any(
            p["requires_ocr"] or p["extraction_state"] == "failed" for p in page_rows
        )
        version.storage_uri = storage_uri
        version.file_size_bytes = len(data)
        version.mime_type = "application/pdf"
        version.ingestion_state = "available"
        version.extraction_state = "requires_review" if requires_review else "ready"
        if requires_review:
            version.review_state = "requires_review"
        provenance = dict(version.provenance or {})
        provenance.update(
            {
                "ingestion_method": "manual_pdf_upload_v1",
                "source_filename_received": filename,
                "checksum_verified": True,
                "page_count": len(page_rows),
                "requires_ocr_page_count": sum(1 for p in page_rows if p["requires_ocr"]),
                "encrypted_requires_review": encrypted_requires_review,
            }
        )
        version.provenance = provenance
        session.commit()
    except Exception:
        session.rollback()
        try:
            if temp_target.exists():
                temp_target.unlink()
        except OSError:
            pass
        # Only remove final file if DB persistence failed during this invocation.
        try:
            if target.exists() and version.storage_uri is None:
                target.unlink()
        except OSError:
            pass
        raise

    session.refresh(version)
    return PdfIngestionSummary(
        version=version,
        page_count=len(page_rows),
        text_page_count=sum(1 for p in page_rows if p["extraction_state"] == "ready"),
        requires_ocr_page_count=sum(1 for p in page_rows if p["requires_ocr"]),
    )


def ingest_acquired_pdf(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> PdfIngestionSummary:
    document, version = _resolve_version(
        session,
        owner=owner,
        project_id=project_id,
        document_id=document_id,
        version_id=version_id,
    )
    settings = get_settings()
    if len(data) > settings.document_upload_max_bytes:
        raise PdfTooLargeError(f"PDF exceeds {settings.document_upload_max_bytes} byte upload limit")
    if len(data) < 5 or not data.startswith(b"%PDF-"):
        raise PdfTypeError("acquired file does not have a PDF signature")
    if content_type and content_type.lower() not in {"application/pdf", "application/octet-stream"}:
        raise PdfTypeError("acquired content type is not PDF")
    if version.source_kind != "acquired":
        raise PlanningDocumentStateError("acquired PDF ingestion is only valid for acquired source versions")
    if version.ingestion_state == "available" or version.storage_uri:
        raise PdfAlreadyIngestedError("document version already has an ingested source artifact")

    actual_checksum = hashlib.sha256(data).hexdigest()
    if actual_checksum != version.checksum_sha256:
        raise PdfChecksumMismatchError("acquired bytes do not match immutable version checksum")
    if version.file_size_bytes is not None and version.file_size_bytes != len(data):
        raise PdfChecksumMismatchError("acquired byte size does not match immutable version metadata")

    page_rows, encrypted_requires_review = _extract_pages(data)
    target, storage_uri = _storage_target(
        project_id=project_id,
        document_id=document.id,
        version_id=version.id,
        checksum=actual_checksum,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_suffix(".pdf.tmp")
    try:
        with open(temp_target, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_target, target)

        session.execute(delete(DocumentPage).where(DocumentPage.document_version_id == version.id))
        for page_data in page_rows:
            session.add(DocumentPage(document_version_id=version.id, **page_data))

        requires_review = encrypted_requires_review or any(
            p["requires_ocr"] or p["extraction_state"] == "failed" for p in page_rows
        )
        version.storage_uri = storage_uri
        version.file_size_bytes = len(data)
        version.mime_type = "application/pdf"
        version.ingestion_state = "available"
        version.extraction_state = "requires_review" if requires_review else "ready"
        if requires_review:
            version.review_state = "requires_review"
        provenance = dict(version.provenance or {})
        provenance.update(
            {
                "ingestion_method": "controlled_acquired_pdf_v1",
                "source_filename_received": filename,
                "checksum_verified": True,
                "page_count": len(page_rows),
                "requires_ocr_page_count": sum(1 for p in page_rows if p["requires_ocr"]),
                "encrypted_requires_review": encrypted_requires_review,
            }
        )
        version.provenance = provenance
        session.commit()
    except Exception:
        session.rollback()
        try:
            if temp_target.exists():
                temp_target.unlink()
        except OSError:
            pass
        # Only remove final file if DB persistence failed during this invocation.
        try:
            if target.exists() and version.storage_uri is None:
                target.unlink()
        except OSError:
            pass
        raise

    session.refresh(version)
    return PdfIngestionSummary(
        version=version,
        page_count=len(page_rows),
        text_page_count=sum(1 for p in page_rows if p["extraction_state"] == "ready"),
        requires_ocr_page_count=sum(1 for p in page_rows if p["requires_ocr"]),
    )


def list_document_pages(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> list[DocumentPage]:
    _, version = _resolve_version(
        session,
        owner=owner,
        project_id=project_id,
        document_id=document_id,
        version_id=version_id,
    )
    return list(
        session.scalars(
            select(DocumentPage)
            .where(DocumentPage.document_version_id == version.id)
            .order_by(DocumentPage.page_number.asc())
        )
    )
