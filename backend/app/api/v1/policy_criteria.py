from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.policy_criterion import (
    PolicyCriterionCreateRequest,
    PolicyCriterionResponse,
    PolicyCriterionReviewRequest,
    PolicyCriterionUpdateRequest,
    PolicyCriterionUseResponse,
)
from app.services.policy_criteria import (
    PolicyCriterionNotFoundError,
    PolicyCriterionProjectNotFoundError,
    PolicyCriterionSourceError,
    PolicyCriterionSourceStaleError,
    PolicyCriterionStateError,
    create_policy_criterion,
    get_policy_criterion,
    list_policy_criteria,
    resolve_policy_criterion_for_use,
    review_policy_criterion,
    update_policy_criterion,
)

router = APIRouter(prefix="/projects/{project_id}/policy-criteria", tags=["policy-criteria"])


def _translate(exc: Exception) -> AppError:
    if isinstance(exc, (PolicyCriterionProjectNotFoundError, PolicyCriterionNotFoundError)):
        return AppError(code="policy_criterion_not_found", message="PolicyCriterion not found.", status_code=404)
    if isinstance(exc, PolicyCriterionSourceStaleError):
        return AppError(code="policy_criterion_source_stale", message=str(exc), status_code=409)
    if isinstance(exc, PolicyCriterionSourceError):
        return AppError(code="policy_criterion_source_unavailable", message=str(exc), status_code=409)
    return AppError(code="policy_criterion_state_invalid", message=str(exc), status_code=409)


@router.post("", response_model=PolicyCriterionResponse, status_code=201)
def create(
    project_id: uuid.UUID,
    payload: PolicyCriterionCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = create_policy_criterion(session, owner=current_user, project_id=project_id, request=payload)
    except (PolicyCriterionProjectNotFoundError, PolicyCriterionSourceError, PolicyCriterionSourceStaleError, PolicyCriterionStateError) as exc:
        raise _translate(exc) from exc
    return PolicyCriterionResponse.model_validate(item)


@router.get("", response_model=list[PolicyCriterionResponse])
def list_items(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    include_archived: bool = Query(False),
):
    try:
        items = list_policy_criteria(session, owner=current_user, project_id=project_id, include_archived=include_archived)
    except (PolicyCriterionProjectNotFoundError, PolicyCriterionStateError) as exc:
        raise _translate(exc) from exc
    return [PolicyCriterionResponse.model_validate(x) for x in items]


@router.get("/{criterion_id}", response_model=PolicyCriterionResponse)
def get_item(
    project_id: uuid.UUID,
    criterion_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = get_policy_criterion(session, owner=current_user, project_id=project_id, criterion_id=criterion_id)
    except (PolicyCriterionProjectNotFoundError, PolicyCriterionNotFoundError, PolicyCriterionStateError) as exc:
        raise _translate(exc) from exc
    return PolicyCriterionResponse.model_validate(item)


@router.patch("/{criterion_id}", response_model=PolicyCriterionResponse)
def update_item(
    project_id: uuid.UUID,
    criterion_id: uuid.UUID,
    payload: PolicyCriterionUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = update_policy_criterion(session, owner=current_user, project_id=project_id, criterion_id=criterion_id, request=payload)
    except (PolicyCriterionProjectNotFoundError, PolicyCriterionNotFoundError, PolicyCriterionStateError) as exc:
        raise _translate(exc) from exc
    return PolicyCriterionResponse.model_validate(item)


@router.post("/{criterion_id}/review", response_model=PolicyCriterionResponse)
def review_item(
    project_id: uuid.UUID,
    criterion_id: uuid.UUID,
    payload: PolicyCriterionReviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = review_policy_criterion(session, owner=current_user, project_id=project_id, criterion_id=criterion_id, request=payload)
    except (PolicyCriterionProjectNotFoundError, PolicyCriterionNotFoundError, PolicyCriterionSourceError, PolicyCriterionSourceStaleError, PolicyCriterionStateError) as exc:
        raise _translate(exc) from exc
    return PolicyCriterionResponse.model_validate(item)


@router.post("/{criterion_id}/resolve", response_model=PolicyCriterionUseResponse)
def resolve_item(
    project_id: uuid.UUID,
    criterion_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item, limitations = resolve_policy_criterion_for_use(session, owner=current_user, project_id=project_id, criterion_id=criterion_id)
    except (PolicyCriterionProjectNotFoundError, PolicyCriterionNotFoundError, PolicyCriterionSourceError, PolicyCriterionSourceStaleError, PolicyCriterionStateError) as exc:
        raise _translate(exc) from exc
    return PolicyCriterionUseResponse(
        criterion=PolicyCriterionResponse.model_validate(item),
        policy_reference_id=item.policy_reference_id,
        limitations=limitations,
    )
