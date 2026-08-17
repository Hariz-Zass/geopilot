from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.compliance_fact import (
    ComplianceFactResponse,
    ComplianceFactUpdateRequest,
    ComplianceFactUseResponse,
    GISDerivedComplianceFactCreateRequest,
    UserSuppliedComplianceFactCreateRequest,
)
from app.services.compliance_facts import (
    ComplianceFactNotFoundError,
    ComplianceFactProjectNotFoundError,
    ComplianceFactSourceError,
    ComplianceFactSourceStaleError,
    ComplianceFactStateError,
    create_gis_derived_fact,
    create_user_supplied_fact,
    get_compliance_fact,
    list_compliance_facts,
    resolve_compliance_fact_for_use,
    set_compliance_fact_archived,
)

router = APIRouter(
    prefix="/projects/{project_id}/sites/{site_id}/compliance-facts",
    tags=["compliance-facts"],
)


def _translate(exc: Exception) -> AppError:
    if isinstance(exc, (ComplianceFactProjectNotFoundError, ComplianceFactNotFoundError)):
        return AppError(code="compliance_fact_not_found", message="ComplianceFact not found.", status_code=404)
    if isinstance(exc, ComplianceFactSourceStaleError):
        return AppError(code="compliance_fact_source_stale", message=str(exc), status_code=409)
    if isinstance(exc, ComplianceFactSourceError):
        return AppError(code="compliance_fact_source_unavailable", message=str(exc), status_code=409)
    return AppError(code="compliance_fact_state_invalid", message=str(exc), status_code=409)


@router.post("/user-supplied", response_model=ComplianceFactResponse, status_code=201)
def create_user_fact(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    payload: UserSuppliedComplianceFactCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = create_user_supplied_fact(
            session, owner=current_user, project_id=project_id, site_id=site_id, request=payload
        )
    except (ComplianceFactProjectNotFoundError, ComplianceFactSourceError, ComplianceFactSourceStaleError, ComplianceFactStateError) as exc:
        raise _translate(exc) from exc
    return ComplianceFactResponse.model_validate(item)


@router.post("/from-gis", response_model=ComplianceFactResponse, status_code=201)
def create_gis_fact(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    payload: GISDerivedComplianceFactCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = create_gis_derived_fact(
            session, owner=current_user, project_id=project_id, site_id=site_id, request=payload
        )
    except (ComplianceFactProjectNotFoundError, ComplianceFactSourceError, ComplianceFactSourceStaleError, ComplianceFactStateError) as exc:
        raise _translate(exc) from exc
    return ComplianceFactResponse.model_validate(item)


@router.get("", response_model=list[ComplianceFactResponse])
def list_items(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    include_archived: bool = Query(False),
):
    try:
        items = list_compliance_facts(
            session,
            owner=current_user,
            project_id=project_id,
            site_id=site_id,
            include_archived=include_archived,
        )
    except (ComplianceFactProjectNotFoundError, ComplianceFactStateError) as exc:
        raise _translate(exc) from exc
    return [ComplianceFactResponse.model_validate(item) for item in items]


@router.get("/{fact_id}", response_model=ComplianceFactResponse)
def get_item(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    fact_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = get_compliance_fact(
            session, owner=current_user, project_id=project_id, site_id=site_id, fact_id=fact_id
        )
    except (ComplianceFactProjectNotFoundError, ComplianceFactNotFoundError, ComplianceFactStateError) as exc:
        raise _translate(exc) from exc
    return ComplianceFactResponse.model_validate(item)


@router.patch("/{fact_id}", response_model=ComplianceFactResponse)
def update_item(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    fact_id: uuid.UUID,
    payload: ComplianceFactUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item = set_compliance_fact_archived(
            session,
            owner=current_user,
            project_id=project_id,
            site_id=site_id,
            fact_id=fact_id,
            is_archived=payload.is_archived,
        )
    except (ComplianceFactProjectNotFoundError, ComplianceFactNotFoundError, ComplianceFactStateError) as exc:
        raise _translate(exc) from exc
    return ComplianceFactResponse.model_validate(item)


@router.post("/{fact_id}/resolve", response_model=ComplianceFactUseResponse)
def resolve_item(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    fact_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        item, limitations = resolve_compliance_fact_for_use(
            session, owner=current_user, project_id=project_id, site_id=site_id, fact_id=fact_id
        )
    except (ComplianceFactProjectNotFoundError, ComplianceFactNotFoundError, ComplianceFactSourceError, ComplianceFactSourceStaleError, ComplianceFactStateError) as exc:
        raise _translate(exc) from exc
    return ComplianceFactUseResponse(fact=ComplianceFactResponse.model_validate(item), limitations=limitations)
