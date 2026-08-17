from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.policy_reference import (
    PolicyReferenceCreateRequest,
    PolicyReferenceResponse,
    PolicyReferenceReviewRequest,
    PolicyReferenceUpdateRequest,
    PolicyReferenceUseResponse,
)
from app.services.policy_references import (
    PolicyReferenceNotFoundError,
    PolicyReferenceProjectNotFoundError,
    PolicyReferenceSourceError,
    PolicyReferenceSourceStaleError,
    PolicyReferenceStateError,
    create_policy_reference,
    get_policy_reference,
    list_policy_references,
    resolve_policy_reference_for_use,
    review_policy_reference,
    update_policy_reference,
)

router = APIRouter(prefix="/projects/{project_id}/policy-references", tags=["policy-references"])


def _translate(exc: Exception) -> AppError:
    if isinstance(exc, (PolicyReferenceProjectNotFoundError, PolicyReferenceNotFoundError)):
        return AppError(code="policy_reference_not_found", message="PolicyReference not found.", status_code=404)
    if isinstance(exc, PolicyReferenceSourceStaleError):
        return AppError(code="policy_reference_source_stale", message=str(exc), status_code=409)
    if isinstance(exc, PolicyReferenceSourceError):
        return AppError(code="policy_reference_source_unavailable", message=str(exc), status_code=409)
    return AppError(code="policy_reference_state_invalid", message=str(exc), status_code=409)


@router.post("", response_model=PolicyReferenceResponse, status_code=201)
def create(
    project_id: uuid.UUID,
    payload: PolicyReferenceCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = create_policy_reference(session, owner=current_user, project_id=project_id, request=payload)
    except (PolicyReferenceProjectNotFoundError, PolicyReferenceSourceError, PolicyReferenceSourceStaleError, PolicyReferenceStateError) as exc:
        raise _translate(exc) from exc
    return PolicyReferenceResponse.model_validate(item)


@router.get("", response_model=list[PolicyReferenceResponse])
def list_items(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    include_archived: bool = Query(False),
):
    try:
        items = list_policy_references(session, owner=current_user, project_id=project_id, include_archived=include_archived)
    except (PolicyReferenceProjectNotFoundError, PolicyReferenceStateError) as exc:
        raise _translate(exc) from exc
    return [PolicyReferenceResponse.model_validate(x) for x in items]


@router.get("/{policy_reference_id}", response_model=PolicyReferenceResponse)
def get_item(
    project_id: uuid.UUID,
    policy_reference_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = get_policy_reference(session, owner=current_user, project_id=project_id, policy_reference_id=policy_reference_id)
    except (PolicyReferenceProjectNotFoundError, PolicyReferenceNotFoundError, PolicyReferenceStateError) as exc:
        raise _translate(exc) from exc
    return PolicyReferenceResponse.model_validate(item)


@router.patch("/{policy_reference_id}", response_model=PolicyReferenceResponse)
def update_item(
    project_id: uuid.UUID,
    policy_reference_id: uuid.UUID,
    payload: PolicyReferenceUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = update_policy_reference(session, owner=current_user, project_id=project_id, policy_reference_id=policy_reference_id, request=payload)
    except (PolicyReferenceProjectNotFoundError, PolicyReferenceNotFoundError, PolicyReferenceStateError) as exc:
        raise _translate(exc) from exc
    return PolicyReferenceResponse.model_validate(item)


@router.post("/{policy_reference_id}/review", response_model=PolicyReferenceResponse)
def review_item(
    project_id: uuid.UUID,
    policy_reference_id: uuid.UUID,
    payload: PolicyReferenceReviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = review_policy_reference(session, owner=current_user, project_id=project_id, policy_reference_id=policy_reference_id, request=payload)
    except (
        PolicyReferenceProjectNotFoundError,
        PolicyReferenceNotFoundError,
        PolicyReferenceStateError,
        PolicyReferenceSourceError,
        PolicyReferenceSourceStaleError,
    ) as exc:
        raise _translate(exc) from exc
    return PolicyReferenceResponse.model_validate(item)


@router.post("/{policy_reference_id}/resolve", response_model=PolicyReferenceUseResponse)
def resolve_item(
    project_id: uuid.UUID,
    policy_reference_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item, source, limitations = resolve_policy_reference_for_use(
            session, owner=current_user, project_id=project_id, policy_reference_id=policy_reference_id
        )
    except (
        PolicyReferenceProjectNotFoundError,
        PolicyReferenceNotFoundError,
        PolicyReferenceStateError,
        PolicyReferenceSourceError,
        PolicyReferenceSourceStaleError,
    ) as exc:
        raise _translate(exc) from exc
    return PolicyReferenceUseResponse(
        policy_reference=PolicyReferenceResponse.model_validate(item),
        source_citation=source,
        limitations=limitations,
    )
