from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.citations import CitationResolveRequest, CitationResolveResponse
from app.services.citations import (
    CitationProjectNotFoundError,
    CitationReferenceStaleError,
    CitationSourceNotFoundError,
    CitationSourceUnavailableError,
    resolve_citations,
)

router = APIRouter(prefix="/projects/{project_id}/citations", tags=["document-citations"])


@router.post("/resolve", response_model=CitationResolveResponse)
def resolve_document_citations(
    project_id: uuid.UUID,
    payload: CitationResolveRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> CitationResolveResponse:
    try:
        citations = resolve_citations(
            session,
            owner=current_user,
            project_id=project_id,
            references=payload.references,
        )
        return CitationResolveResponse(citations=citations)
    except (CitationProjectNotFoundError, CitationSourceNotFoundError) as exc:
        raise AppError(code="citation_source_not_found", message="Citation source not found.", status_code=404) from exc
    except CitationReferenceStaleError as exc:
        raise AppError(code="citation_reference_stale", message=str(exc), status_code=409) from exc
    except CitationSourceUnavailableError as exc:
        raise AppError(code="citation_source_unavailable", message=str(exc), status_code=409) from exc
