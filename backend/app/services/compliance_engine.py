from __future__ import annotations

import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.compliance_engine import ComplianceEvaluationResponse
from app.services.policy_criteria import resolve_policy_criterion_for_use, PolicyCriterionStateError, PolicyCriterionNotFoundError
from app.services.compliance_facts import resolve_compliance_fact_for_use, ComplianceFactStateError, ComplianceFactNotFoundError, ComplianceFactSourceStaleError

class ComplianceEvaluationError(Exception):
    pass


def _eq_text(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def _evaluate_numeric(op: str, observed: Decimal, threshold: Decimal | None, lower: Decimal | None, upper: Decimal | None) -> bool | None:
    if op == "eq": return observed == threshold
    if op == "ne": return observed != threshold
    if op == "gt": return observed > threshold
    if op == "gte": return observed >= threshold
    if op == "lt": return observed < threshold
    if op == "lte": return observed <= threshold
    if op == "between": return lower <= observed <= upper  # type: ignore[operator]
    return None


def evaluate_compliance(session: Session, *, owner: User, project_id: uuid.UUID, site_id: uuid.UUID, criterion_id: uuid.UUID, fact_id: uuid.UUID) -> ComplianceEvaluationResponse:
    try:
        criterion, c_limits = resolve_policy_criterion_for_use(session, owner=owner, project_id=project_id, criterion_id=criterion_id)
        fact, f_limits = resolve_compliance_fact_for_use(session, owner=owner, project_id=project_id, site_id=site_id, fact_id=fact_id)
    except (PolicyCriterionStateError, PolicyCriterionNotFoundError, ComplianceFactStateError, ComplianceFactNotFoundError, ComplianceFactSourceStaleError) as exc:
        raise ComplianceEvaluationError(str(exc)) from exc

    limitations = [*c_limits, *f_limits, "This deterministic comparison is evidence-oriented and is not statutory compliance, legal certification, or development approval."]
    outcome = "unresolved"
    if criterion.metric_key != fact.metric_key:
        limitations.append("Criterion metric_key and ComplianceFact metric_key do not match.")
    elif criterion.value_type != fact.value_type:
        limitations.append("Criterion and ComplianceFact value types do not match.")
    elif (criterion.unit or None) != (fact.unit or None):
        limitations.append("Criterion and ComplianceFact units do not match; unit conversion is not implicit.")
    elif criterion.operator == "manual_review":
        limitations.append("This criterion explicitly requires manual professional review.")
    else:
        matched: bool | None = None
        if criterion.value_type == "numeric" and fact.numeric_value is not None:
            matched = _evaluate_numeric(criterion.operator, fact.numeric_value, criterion.threshold_numeric, criterion.lower_numeric, criterion.upper_numeric)
        elif criterion.value_type == "text" and fact.text_value is not None and criterion.expected_text is not None:
            eq = _eq_text(fact.text_value, criterion.expected_text); matched = eq if criterion.operator == "eq" else not eq
        elif criterion.value_type == "boolean" and fact.boolean_value is not None:
            matched = fact.boolean_value is criterion.expected_boolean
        elif criterion.value_type == "set" and fact.set_value is not None and criterion.expected_values is not None:
            observed = {x.casefold() for x in fact.set_value}; expected = {x.casefold() for x in criterion.expected_values}
            contained = bool(observed & expected); matched = contained if criterion.operator == "in" else not contained
        if matched is not None:
            outcome = "evidence_indicates_compliance" if matched else "evidence_indicates_non_compliance"
        else:
            limitations.append("The criterion/fact payload could not be deterministically evaluated.")

    return ComplianceEvaluationResponse(
        outcome=outcome, operator=criterion.operator, metric_key=criterion.metric_key, unit=criterion.unit,
        observed_numeric=fact.numeric_value, threshold_numeric=criterion.threshold_numeric, lower_numeric=criterion.lower_numeric, upper_numeric=criterion.upper_numeric,
        observed_text=fact.text_value, expected_text=criterion.expected_text, observed_boolean=fact.boolean_value, expected_boolean=criterion.expected_boolean,
        observed_set=fact.set_value, expected_values=criterion.expected_values, policy_criterion_id=criterion.id, compliance_fact_id=fact.id, limitations=limitations,
    )
