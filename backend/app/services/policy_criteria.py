from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.policy_criterion import PolicyCriterion
from app.models.user import User
from app.schemas.policy_criterion import (
    PolicyCriterionCreateRequest,
    PolicyCriterionReviewRequest,
    PolicyCriterionUpdateRequest,
)
from app.services.isolation import ProjectScopeNotFoundError, ProjectState, ScopeStateError, resolve_project_scope
from app.services.policy_references import (
    PolicyReferenceNotFoundError,
    PolicyReferenceProjectNotFoundError,
    PolicyReferenceSourceError,
    PolicyReferenceSourceStaleError,
    PolicyReferenceStateError,
    resolve_policy_reference_for_use,
)


class PolicyCriterionProjectNotFoundError(Exception):
    pass


class PolicyCriterionNotFoundError(Exception):
    pass


class PolicyCriterionStateError(Exception):
    pass


class PolicyCriterionSourceError(Exception):
    pass


class PolicyCriterionSourceStaleError(Exception):
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
        raise PolicyCriterionProjectNotFoundError from exc
    except ScopeStateError as exc:
        raise PolicyCriterionStateError(str(exc)) from exc


def _get(session: Session, *, owner: User, project_id: uuid.UUID, criterion_id: uuid.UUID) -> PolicyCriterion:
    project = _project(session, owner=owner, project_id=project_id)
    item = session.scalar(
        select(PolicyCriterion).where(
            PolicyCriterion.id == criterion_id,
            PolicyCriterion.project_id == project.id,
        )
    )
    if item is None:
        raise PolicyCriterionNotFoundError
    return item


def _resolve_parent(session: Session, *, owner: User, project_id: uuid.UUID, policy_reference_id: uuid.UUID):
    try:
        return resolve_policy_reference_for_use(
            session,
            owner=owner,
            project_id=project_id,
            policy_reference_id=policy_reference_id,
        )
    except (PolicyReferenceProjectNotFoundError, PolicyReferenceNotFoundError) as exc:
        raise PolicyCriterionSourceError("Verified PolicyReference not found.") from exc
    except PolicyReferenceSourceStaleError as exc:
        raise PolicyCriterionSourceStaleError(str(exc)) from exc
    except (PolicyReferenceSourceError, PolicyReferenceStateError) as exc:
        raise PolicyCriterionSourceError(str(exc)) from exc


_NUMBER_RE = re.compile(r"(?<![\w.])[-+]?\d+(?:[,.]\d+)*(?![\w.])")


def _numbers_in(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for token in _NUMBER_RE.findall(text):
        cleaned = token.replace(",", "")
        try:
            values.add(Decimal(cleaned))
        except InvalidOperation:
            continue
    return values


def _validate_grounding(request: PolicyCriterionCreateRequest, source_wording: str) -> None:
    evidence = request.source_evidence_text.strip()
    if evidence not in source_wording:
        raise PolicyCriterionSourceError("source_evidence_text must be an exact passage from the verified PolicyReference source wording.")

    if request.value_type == "numeric":
        observed = _numbers_in(evidence)
        required = (
            {request.lower_numeric, request.upper_numeric}
            if request.operator == "between"
            else {request.threshold_numeric}
        )
        if any(value not in observed for value in required if value is not None):
            raise PolicyCriterionSourceError("Numeric threshold/bounds must be explicitly present in source_evidence_text.")
    elif request.value_type == "text" and request.expected_text:
        if request.expected_text.casefold() not in evidence.casefold():
            raise PolicyCriterionSourceError("expected_text must be explicitly present in source_evidence_text.")
    elif request.value_type == "set" and request.expected_values:
        missing = [value for value in request.expected_values if value.casefold() not in evidence.casefold()]
        if missing:
            raise PolicyCriterionSourceError("Every expected_values item must be explicitly present in source_evidence_text.")
    elif request.value_type == "boolean":
        # Boolean policy meaning is interpretive; it is reviewable but never inferred from arbitrary text here.
        if not request.interpretation_notes:
            raise PolicyCriterionSourceError("Boolean criteria require interpretation_notes explaining the source-grounded mapping.")


def create_policy_criterion(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    request: PolicyCriterionCreateRequest,
) -> PolicyCriterion:
    project = _project(session, owner=owner, project_id=project_id, active=True)
    policy_reference, source, _limitations = _resolve_parent(
        session,
        owner=owner,
        project_id=project_id,
        policy_reference_id=request.policy_reference_id,
    )
    if policy_reference.project_id != project.id:
        raise PolicyCriterionSourceError("PolicyReference is outside the active project scope.")
    _validate_grounding(request, policy_reference.source_wording)

    item = PolicyCriterion(
        project_id=project.id,
        policy_reference_id=policy_reference.id,
        created_by_user_id=owner.id,
        code=request.code.strip(),
        label=request.label.strip(),
        metric_key=request.metric_key.strip(),
        value_type=request.value_type,
        operator=request.operator,
        unit=request.unit.strip() if request.unit else None,
        threshold_numeric=request.threshold_numeric,
        lower_numeric=request.lower_numeric,
        upper_numeric=request.upper_numeric,
        expected_text=request.expected_text.strip() if request.expected_text else None,
        expected_boolean=request.expected_boolean,
        expected_values=request.expected_values,
        source_evidence_text=request.source_evidence_text.strip(),
        interpretation_notes=request.interpretation_notes,
        applicability_notes=request.applicability_notes,
        representation_state="draft",
        review_state="unreviewed",
        is_archived=False,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise PolicyCriterionStateError("PolicyCriterion code must be unique within a project.") from exc
    session.refresh(item)
    return item


def list_policy_criteria(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    include_archived: bool = False,
) -> list[PolicyCriterion]:
    project = _project(session, owner=owner, project_id=project_id)
    stmt = select(PolicyCriterion).where(PolicyCriterion.project_id == project.id)
    if not include_archived:
        stmt = stmt.where(PolicyCriterion.is_archived.is_(False))
    return list(session.scalars(stmt.order_by(PolicyCriterion.created_at, PolicyCriterion.id)))


def get_policy_criterion(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    criterion_id: uuid.UUID,
) -> PolicyCriterion:
    return _get(session, owner=owner, project_id=project_id, criterion_id=criterion_id)


def update_policy_criterion(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    criterion_id: uuid.UUID,
    request: PolicyCriterionUpdateRequest,
) -> PolicyCriterion:
    item = _get(session, owner=owner, project_id=project_id, criterion_id=criterion_id)
    _project(session, owner=owner, project_id=project_id, active=True)
    changes = request.model_dump(exclude_unset=True)
    if item.representation_state == "final":
        illegal = set(changes) - {"is_archived"}
        if illegal:
            raise PolicyCriterionStateError("Final PolicyCriterion content is immutable; only archive state may change.")
    for key, value in changes.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(item, key, value)
    session.commit()
    session.refresh(item)
    return item


def review_policy_criterion(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    criterion_id: uuid.UUID,
    request: PolicyCriterionReviewRequest,
) -> PolicyCriterion:
    item = _get(session, owner=owner, project_id=project_id, criterion_id=criterion_id)
    _project(session, owner=owner, project_id=project_id, active=True)
    if item.is_archived:
        raise PolicyCriterionStateError("Archived PolicyCriterion cannot be reviewed.")
    if item.representation_state == "final":
        raise PolicyCriterionStateError("Final PolicyCriterion cannot be reviewed again.")

    if request.action == "verify":
        parent, _source, _limitations = _resolve_parent(
            session,
            owner=owner,
            project_id=project_id,
            policy_reference_id=item.policy_reference_id,
        )
        # Reconstruct the material rule shape and re-run grounding against current source.
        reconstructed = PolicyCriterionCreateRequest(
            policy_reference_id=item.policy_reference_id,
            code=item.code,
            label=item.label,
            metric_key=item.metric_key,
            value_type=item.value_type,
            operator=item.operator,
            unit=item.unit,
            threshold_numeric=item.threshold_numeric,
            lower_numeric=item.lower_numeric,
            upper_numeric=item.upper_numeric,
            expected_text=item.expected_text,
            expected_boolean=item.expected_boolean,
            expected_values=item.expected_values,
            source_evidence_text=item.source_evidence_text,
            interpretation_notes=item.interpretation_notes,
            applicability_notes=item.applicability_notes,
        )
        _validate_grounding(reconstructed, parent.source_wording)
        item.representation_state = "final"
        item.review_state = "verified"
    elif request.action == "reject":
        item.representation_state = "final"
        item.review_state = "rejected"
    else:
        item.representation_state = "draft"
        item.review_state = "requires_review"

    item.reviewed_by_user_id = owner.id
    item.reviewed_at = datetime.now(timezone.utc)
    item.review_notes = request.review_notes
    session.commit()
    session.refresh(item)
    return item


def resolve_policy_criterion_for_use(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    criterion_id: uuid.UUID,
) -> tuple[PolicyCriterion, list[str]]:
    item = _get(session, owner=owner, project_id=project_id, criterion_id=criterion_id)
    _project(session, owner=owner, project_id=project_id, active=True)
    if item.is_archived:
        raise PolicyCriterionStateError("Archived PolicyCriterion is unavailable for deterministic use.")
    if item.representation_state != "final" or item.review_state != "verified":
        raise PolicyCriterionStateError("Only final, verified PolicyCriterion records may be used by deterministic engines.")

    parent, _source, parent_limitations = _resolve_parent(
        session,
        owner=owner,
        project_id=project_id,
        policy_reference_id=item.policy_reference_id,
    )
    reconstructed = PolicyCriterionCreateRequest(
        policy_reference_id=item.policy_reference_id,
        code=item.code,
        label=item.label,
        metric_key=item.metric_key,
        value_type=item.value_type,
        operator=item.operator,
        unit=item.unit,
        threshold_numeric=item.threshold_numeric,
        lower_numeric=item.lower_numeric,
        upper_numeric=item.upper_numeric,
        expected_text=item.expected_text,
        expected_boolean=item.expected_boolean,
        expected_values=item.expected_values,
        source_evidence_text=item.source_evidence_text,
        interpretation_notes=item.interpretation_notes,
        applicability_notes=item.applicability_notes,
    )
    _validate_grounding(reconstructed, parent.source_wording)
    limitations = list(parent_limitations)
    limitations.append("PolicyCriterion is a reviewed deterministic rule representation, not statutory approval or legal certification.")
    if item.applicability_notes:
        limitations.append("Criterion applicability is bounded by applicability_notes and requires planner judgment where material.")
    return item, limitations
