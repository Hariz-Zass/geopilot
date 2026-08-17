from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.document_retrieval import DocumentSearchRequest, DocumentSearchResponse
from app.services.document_retrieval import (
    DocumentRetrievalProjectNotFoundError,
    DocumentRetrievalStateError,
    search_documents,
)

router = APIRouter(prefix="/projects/{project_id}/document-search", tags=["document-retrieval"])


@router.post("", response_model=DocumentSearchResponse)
def search(
    project_id: uuid.UUID,
    payload: DocumentSearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        return search_documents(session, owner=current_user, project_id=project_id, request=payload)
    except DocumentRetrievalProjectNotFoundError as exc:
        raise AppError(code="project_not_found", message="Project not found.", status_code=404) from exc
    except DocumentRetrievalStateError as exc:
        raise AppError(code="document_retrieval_state_invalid", message=str(exc), status_code=409) from exc
