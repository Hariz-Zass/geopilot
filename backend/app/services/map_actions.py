from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.map_action import MapAction, ResolvedMapAction
from app.services.geometry_references import resolve_geometry_reference


class MapActionResolutionError(Exception):
    """Map action could not be resolved into a complete server-authoritative payload."""


def resolve_map_action(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    map_action: MapAction,
) -> ResolvedMapAction:
    """Resolve every GeometryReference in a MapAction through the canonical resolver.

    Resolution is all-or-nothing. The service never accepts client-supplied geometry and
    never silently skips unavailable or stale references.
    """

    resolutions = []
    for reference in map_action.geometry_references:
        # Fast rejection before any authoritative query. This also prevents a map action
        # from combining references belonging to different projects.
        if reference.project_id != project_id:
            from app.services.geometry_references import GeometryReferenceNotFoundError

            raise GeometryReferenceNotFoundError
        resolutions.append(
            resolve_geometry_reference(
                session,
                owner=owner,
                project_id=project_id,
                reference=reference,
            )
        )

    try:
        return ResolvedMapAction(
            map_action=map_action,
            resolved_geometries=resolutions,
        )
    except ValueError as exc:  # defensive Pydantic/value boundary
        raise MapActionResolutionError("resolved map action payload is inconsistent") from exc
