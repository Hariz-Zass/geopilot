from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.planning_document import DocumentPage, DocumentVersion
from app.models.user import User
from app.services.document_ocr import OcrPageResult, ocr_pdf_page
from app.services.planning_documents import get_document_version


class DocumentOcrRemediationError(Exception):
    pass


def _resolve_local_pdf_path(version: DocumentVersion) -> Path:
    storage_uri = version.storage_uri or ""
    prefix = "local://documents/"

    if not storage_uri.startswith(prefix):
        raise DocumentOcrRemediationError(
            "document version does not use local document storage"
        )

    relative = storage_uri[len(prefix):]

    root = Path(
        get_settings().document_storage_root
    ).expanduser().resolve()

    path = (root / relative).resolve()

    if root != path and root not in path.parents:
        raise DocumentOcrRemediationError(
            "resolved document path escapes storage root"
        )

    if not path.is_file():
        raise DocumentOcrRemediationError(
            "stored document PDF does not exist"
        )

    return path


def remediate_document_page_with_ocr(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    page_number: int,
) -> tuple[DocumentPage, OcrPageResult]:
    version = get_document_version(
        session,
        owner=owner,
        project_id=project_id,
        document_id=document_id,
        version_id=version_id,
    )

    page = session.scalar(
        select(DocumentPage).where(
            DocumentPage.document_version_id == version.id,
            DocumentPage.page_number == page_number,
        )
    )

    if page is None:
        raise DocumentOcrRemediationError(
            "document page does not exist"
        )

    if (
        page.extraction_state == "ready"
        and not page.requires_ocr
        and page.extracted_text.strip()
    ):
        raise DocumentOcrRemediationError(
            "document page already contains validated extracted text"
        )

    pdf_path = _resolve_local_pdf_path(version)

    result = ocr_pdf_page(
        pdf_path,
        page_number=page_number,
    )

    text = result.text.strip()

    if not text:
        raise DocumentOcrRemediationError(
            "OCR produced no usable text"
        )

    digest = hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()

    page.extracted_text = text
    page.text_sha256 = digest
    page.char_count = len(text)
    page.extraction_method = "tesseract_ocr_v1"
    page.extraction_state = "ready"
    page.requires_ocr = False

    session.commit()
    session.refresh(page)

    return page, result
