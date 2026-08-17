from __future__ import annotations
from app.schemas.tool_evidence import ToolEvidence
from app.schemas.map_action import MapAction

def map_action_for_evidence(evidence: ToolEvidence, *, action_type="highlight"):
    if not evidence.geometry_reference:
        return None
    return MapAction(action=action_type, geometry_references=[evidence.geometry_reference])
