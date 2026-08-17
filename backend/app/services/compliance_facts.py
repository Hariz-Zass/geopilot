from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.compliance_fact import ComplianceFact
from app.models.gis_feature import GISFeature
from app.models.user import User
from app.schemas.compliance_fact import (
    GISDerivedComplianceFactCreateRequest,
    UserSuppliedComplianceFactCreateRequest,
)
from app.services.gis_analysis import (
    GISAnalysisResultError,
    GISAnalysisStateError,
    calculate_feature_distance,
    calculate_site_area,
)
from app.services.gis_features import GISFeatureNotFoundError, get_gis_feature
from app.services.gis_layers import GISLayerNotFoundError, get_gis_layer
from app.services.isolation import (
    ProjectScopeNotFoundError,
    ProjectState,
    ScopeStateError,
    SiteScopeNotFoundError,
    SiteState,
    resolve_analysis_scope,
    resolve_site_scope,
)


class ComplianceFactNotFoundError(Exception):
    pass


class ComplianceFactProjectNotFoundError(Exception):
    pass


class ComplianceFactStateError(Exception):
    pass


class ComplianceFactSourceError(Exception):
    pass


class ComplianceFactSourceStaleError(Exception):
    pass


def _scope(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    active: bool = True,
):
    try:
        if active:
            return resolve_analysis_scope(
                session, owner=owner, project_id=project_id, site_id=site_id
            )
        return resolve_site_scope(
            session,
            owner=owner,
            project_id=project_id,
            site_id=site_id,
            project_state=ProjectState.ANY,
            site_state=SiteState.ANY,
        )
    except (ProjectScopeNotFoundError, SiteScopeNotFoundError) as exc:
        raise ComplianceFactProjectNotFoundError from exc
    except ScopeStateError as exc:
        raise ComplianceFactStateError(str(exc)) from exc


def _canonical_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def _provenance_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _get(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    fact_id: uuid.UUID,
) -> ComplianceFact:
    # Resolve owned project/site first so resource existence is never leaked.
    _scope(session, owner=owner, project_id=project_id, site_id=site_id, active=False)
    fact = session.scalar(
        select(ComplianceFact).where(
            ComplianceFact.id == fact_id,
            ComplianceFact.project_id == project_id,
            ComplianceFact.site_id == site_id,
        )
    )
    if fact is None:
        raise ComplianceFactNotFoundError
    return fact


def create_user_supplied_fact(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    request: UserSuppliedComplianceFactCreateRequest,
) -> ComplianceFact:
    scope = _scope(session, owner=owner, project_id=project_id, site_id=site_id)
    details = {
        "evidence_authority": "owner_assertion",
        "independently_measured": False,
    }
    identity = {
        "project_id": str(project_id),
        "site_id": str(site_id),
        "site_geometry_hash": scope.site.geometry_hash,
        "site_geometry_revision": scope.site.geometry_revision,
        "metric_key": request.metric_key,
        "value_type": request.value_type,
        "unit": request.unit,
        "numeric_value": _canonical_decimal(request.numeric_value),
        "text_value": request.text_value,
        "boolean_value": request.boolean_value,
        "set_value": request.set_value,
        "source_kind": "user_supplied",
        "source_method": "owner_assertion_v1",
        "source_description": request.source_description,
        "created_by_user_id": str(owner.id),
    }
    item = ComplianceFact(
        project_id=project_id,
        site_id=site_id,
        created_by_user_id=owner.id,
        metric_key=request.metric_key,
        label=request.label.strip(),
        value_type=request.value_type,
        unit=request.unit.strip() if request.unit else None,
        numeric_value=request.numeric_value,
        text_value=request.text_value.strip() if request.text_value else None,
        boolean_value=request.boolean_value,
        set_value=request.set_value,
        source_kind="user_supplied",
        source_method="owner_assertion_v1",
        source_description=request.source_description.strip(),
        source_details=details,
        site_geometry_hash=scope.site.geometry_hash,
        site_geometry_revision=scope.site.geometry_revision,
        provenance_hash=_provenance_hash(identity),
        is_archived=False,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ComplianceFactStateError(
            "An identical ComplianceFact provenance record already exists."
        ) from exc
    session.refresh(item)
    return item


def create_gis_derived_fact(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    request: GISDerivedComplianceFactCreateRequest,
) -> ComplianceFact:
    scope = _scope(session, owner=owner, project_id=project_id, site_id=site_id)
    try:
        if request.analysis_type == "site_area":
            result = calculate_site_area(
                session, owner=owner, project_id=project_id, site_id=site_id
            )
            numeric = Decimal(str(getattr(result, request.output_field)))
            unit = "sqm" if request.output_field == "area_sqm" else "hectares"
            layer_id = None
            feature_id = None
            feature_hash = None
            details = {
                "analysis_type": result.analysis_type,
                "output_field": request.output_field,
                "deterministic": result.deterministic,
            }
        else:
            assert request.layer_id is not None and request.feature_id is not None
            result = calculate_feature_distance(
                session,
                owner=owner,
                project_id=project_id,
                site_id=site_id,
                layer_id=request.layer_id,
                feature_id=request.feature_id,
            )
            numeric = Decimal(str(result.distance_m))
            unit = "m"
            layer_id = result.layer_id
            feature_id = result.feature_id
            feature_hash = result.feature_geometry_hash
            details = {
                "analysis_type": result.analysis_type,
                "output_field": request.output_field,
                "deterministic": result.deterministic,
            }
    except (GISAnalysisStateError, GISAnalysisResultError, GISFeatureNotFoundError, GISLayerNotFoundError) as exc:
        raise ComplianceFactSourceError(str(exc)) from exc

    if result.project_id != project_id or result.site_id != site_id:
        raise ComplianceFactSourceError("Deterministic GIS result escaped the requested project/site scope.")
    if result.site_geometry_hash != scope.site.geometry_hash or result.site_geometry_revision != scope.site.geometry_revision:
        raise ComplianceFactSourceStaleError("Deterministic GIS result does not match the current Site geometry identity.")

    description = request.source_description or f"Server-derived {request.analysis_type}.{request.output_field} measurement."
    identity = {
        "project_id": str(project_id),
        "site_id": str(site_id),
        "site_geometry_hash": result.site_geometry_hash,
        "site_geometry_revision": result.site_geometry_revision,
        "metric_key": request.metric_key,
        "value_type": "numeric",
        "unit": unit,
        "numeric_value": _canonical_decimal(numeric),
        "source_kind": "gis_analysis",
        "source_method": result.method_version,
        "analysis_type": request.analysis_type,
        "output_field": request.output_field,
        "layer_id": str(layer_id) if layer_id else None,
        "feature_id": str(feature_id) if feature_id else None,
        "feature_geometry_hash": feature_hash,
    }
    item = ComplianceFact(
        project_id=project_id,
        site_id=site_id,
        created_by_user_id=owner.id,
        metric_key=request.metric_key,
        label=request.label.strip(),
        value_type="numeric",
        unit=unit,
        numeric_value=numeric,
        source_kind="gis_analysis",
        source_method=result.method_version,
        source_description=description.strip(),
        source_details=details,
        site_geometry_hash=result.site_geometry_hash,
        site_geometry_revision=result.site_geometry_revision,
        source_gis_layer_id=layer_id,
        source_gis_feature_id=feature_id,
        source_feature_geometry_hash=feature_hash,
        provenance_hash=_provenance_hash(identity),
        is_archived=False,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ComplianceFactStateError(
            "An identical ComplianceFact provenance record already exists."
        ) from exc
    session.refresh(item)
    return item


def list_compliance_facts(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    include_archived: bool = False,
) -> list[ComplianceFact]:
    _scope(session, owner=owner, project_id=project_id, site_id=site_id, active=False)
    stmt = select(ComplianceFact).where(
        ComplianceFact.project_id == project_id,
        ComplianceFact.site_id == site_id,
    )
    if not include_archived:
        stmt = stmt.where(ComplianceFact.is_archived.is_(False))
    return list(session.scalars(stmt.order_by(ComplianceFact.created_at, ComplianceFact.id)))


def get_compliance_fact(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    fact_id: uuid.UUID,
) -> ComplianceFact:
    return _get(
        session, owner=owner, project_id=project_id, site_id=site_id, fact_id=fact_id
    )


def set_compliance_fact_archived(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    fact_id: uuid.UUID,
    is_archived: bool,
) -> ComplianceFact:
    item = _get(
        session, owner=owner, project_id=project_id, site_id=site_id, fact_id=fact_id
    )
    item.is_archived = is_archived
    session.commit()
    session.refresh(item)
    return item


def _verify_feature_lineage(
    session: Session,
    *,
    owner: User,
    fact: ComplianceFact,
) -> None:
    if fact.source_gis_feature_id is None:
        return
    assert fact.source_gis_layer_id is not None
    try:
        layer = get_gis_layer(
            session,
            owner=owner,
            project_id=fact.project_id,
            layer_id=fact.source_gis_layer_id,
        )
        feature: GISFeature = get_gis_feature(
            session,
            owner=owner,
            project_id=fact.project_id,
            layer_id=fact.source_gis_layer_id,
            feature_id=fact.source_gis_feature_id,
        )
    except (GISLayerNotFoundError, GISFeatureNotFoundError) as exc:
        raise ComplianceFactSourceStaleError("GIS evidence source is no longer resolvable.") from exc
    if layer.is_archived or not layer.is_active or feature.is_archived:
        raise ComplianceFactSourceStaleError("GIS evidence source is no longer active and available.")
    if feature.geometry_hash != fact.source_feature_geometry_hash:
        raise ComplianceFactSourceStaleError("GISFeature geometry identity has changed since the fact was measured.")


def resolve_compliance_fact_for_use(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    fact_id: uuid.UUID,
) -> tuple[ComplianceFact, list[str]]:
    item = _get(
        session, owner=owner, project_id=project_id, site_id=site_id, fact_id=fact_id
    )
    if item.is_archived:
        raise ComplianceFactStateError("Archived ComplianceFact is unavailable for deterministic use.")

    scope = _scope(session, owner=owner, project_id=project_id, site_id=site_id)
    if (
        item.site_geometry_hash != scope.site.geometry_hash
        or item.site_geometry_revision != scope.site.geometry_revision
    ):
        raise ComplianceFactSourceStaleError(
            "Site geometry identity has changed since this ComplianceFact was recorded."
        )
    _verify_feature_lineage(session, owner=owner, fact=item)

    limitations: list[str] = []
    if item.source_kind == "user_supplied":
        limitations.append(
            "This fact is an owner-supplied assertion and has not been independently measured by GeoPilot AI."
        )
    else:
        limitations.append(
            "This fact is a deterministic GIS measurement and remains valid only for the recorded source geometry identities."
        )
    limitations.append(
        "A validated ComplianceFact is evidence only; it is not a compliance finding, statutory conclusion, or development approval."
    )
    return item, limitations
