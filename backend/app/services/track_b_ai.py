from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.provider_resilience import ProviderResilienceError, generate_with_failover


class TrackBAIError(Exception):
    pass


def _manifest(project_id: uuid.UUID, analysis_id: uuid.UUID) -> tuple[Path, dict[str, Any]]:
    root = Path(get_settings().raster_storage_root).expanduser().resolve()
    path = (root / "analysis" / str(project_id) / str(analysis_id) / "analysis.json").resolve()
    if root != path and root not in path.parents:
        raise TrackBAIError("Analysis path escaped configured root.")
    if not path.is_file():
        raise TrackBAIError("Track B analysis manifest not found.")
    return path, json.loads(path.read_text(encoding="utf-8"))


def _allowed_numeric_tokens(data: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    keys = (
        "usable_coverage_percent", "changed_pixel_count", "valid_pixel_count",
        "changed_percentage", "changed_area_hectares", "mean_before", "mean_after",
    )
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.add(str(value))
            values.add(f"{float(value):.1f}")
            values.add(f"{float(value):.2f}")
            values.add(f"{float(value):.3f}")
            values.add(f"{float(value):.4f}")
            values.add(f"{float(value):.5f}")
            values.add(f"{float(value):.6f}")
            values.add(f"{float(value):.7f}")
            values.add(f"{float(value):.8f}")
    # Calendar dates are source metadata, not invented measurements.
    for key in ("before_datetime", "after_datetime"):
        value = data.get(key)
        if isinstance(value, str):
            values.update(re.findall(r"\d+(?:\.\d+)?", value))
    return values


# TRACKB_NUMERIC_ALLOWLIST_V2
def _numeric_allowlist_block(*analyses: dict[str, Any]) -> str:
    allowed: set[str] = set()
    for analysis in analyses:
        allowed |= _allowed_numeric_tokens(analysis)
    ordered = sorted(allowed, key=lambda x: (len(x), x))
    return (
        "\n\nSTRICT NUMERIC OUTPUT CONTRACT:\n"
        "Any numeric token containing digits in your JSON narrative MUST be copied exactly "
        "from the following allowlist. If a number you want to mention is not present, rewrite "
        "the sentence qualitatively without that number. Do NOT mention generic NDVI scale "
        "bounds, zero/one reference values, thresholds, numbered steps, ranks, counts, or other "
        "numeric conventions unless that exact token appears below. Before returning JSON, scan "
        "every narrative string and remove or rewrite any digit token not in this allowlist.\n"
        "ALLOWED_NUMERIC_TOKENS: " + ", ".join(ordered)
    )


def _validate_no_invented_numbers(payload: dict[str, Any], analysis: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    allowed = _allowed_numeric_tokens(analysis)
    # Ignore tiny ordinal/list-like integers and evidence UUID digits by validating narrative fields only.
    narrative = " ".join([
        str(payload.get("executive_summary", "")), str(payload.get("planner_problem", "")),
        *[str(x) for x in payload.get("next_actions", [])], *[str(x) for x in payload.get("caveats", [])],
        *[str(i.get(k, "")) for i in payload.get("insights", []) for k in ("finding", "planning_relevance", "recommended_action")],
    ])
    narrative = _remove_leading_list_markers(narrative)
    for token in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", narrative):
        if token not in allowed:
            raise TrackBAIError(f"AI interpretation introduced an ungrounded numeric claim: {token}")


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise TrackBAIError("AI provider did not return valid structured JSON.") from exc
    if not isinstance(value, dict):
        raise TrackBAIError("AI provider returned an invalid interpretation object.")
    return value
# TRACKB_OPENAI_CONTRACT_PATCH_V1
def _canonicalize_list_fields(
    payload: dict[str, Any],
    *,
    string_fields: tuple[str, ...] = (),
    object_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Normalize harmless JSON container-shape drift without changing evidence content."""
    for key in string_fields:
        value = payload.get(key)
        if value is None:
            payload[key] = []
        elif isinstance(value, str):
            payload[key] = [value]
    for key in object_fields:
        value = payload.get(key)
        if value is None:
            payload[key] = []
        elif isinstance(value, dict):
            payload[key] = [value]
    return payload


def _remove_leading_list_markers(text: str) -> str:
    """Ignore presentation-only markers like '1.'/'2)' but keep real numeric claims."""
    return re.sub(r"(^|\s)\d{1,2}[.)]\s+", r"\1", text)


def interpret_track_b_analysis(*, project_id: uuid.UUID, analysis_id: uuid.UUID) -> dict[str, Any]:
    path, analysis = _manifest(project_id, analysis_id)
    evidence = analysis.get("evidence") or []
    if not evidence:
        raise TrackBAIError("AI operation requires an evidence payload with provenance.")

    facts = {
        "analysis_id": str(analysis_id),
        "mode": analysis.get("mode"), "method": analysis.get("method"),
        "before_datetime": analysis.get("before_datetime"), "after_datetime": analysis.get("after_datetime"),
        "usable_coverage_percent": analysis.get("usable_coverage_percent"),
        "changed_pixel_count": analysis.get("changed_pixel_count"), "valid_pixel_count": analysis.get("valid_pixel_count"),
        "changed_percentage": analysis.get("changed_percentage"), "changed_area_hectares": analysis.get("changed_area_hectares"),
        "mean_before": analysis.get("mean_before"), "mean_after": analysis.get("mean_after"),
        "limitations": analysis.get("limitations") or [], "evidence": evidence,
    }
    instructions = """You are GeoPilot AI, a specialist town-planning decision-support copilot for a geospatial and satellite AI challenge. Interpret ONLY the supplied deterministic facts. Never invent a measurement, land-use class, cause, statutory rule, external fact, location fact, or recommendation premise. Distinguish measured change from possible planning relevance. Do not claim causation from spectral change alone. Recommendations must be actions a town planner can take using the supplied evidence: investigate, prioritize field verification, compare organizer layers, flag an area for review, or request professional assessment. Do not issue planning approval, legal certification, or statutory conclusions. NUMERIC GROUNDING RULE: every numeric token containing digits must be copied from a supplied deterministic fact or be a normal rounded display of that same fact. Never invent numbered steps, numeric ranks, action counts, zone counts, or numeric labels; use words instead of digits for non-measurement enumeration. Return JSON only with exactly these keys: confidence (high|moderate|limited), executive_summary, planner_problem, insights, next_actions, caveats. insights MUST be an array of objects containing exactly title, finding, planning_relevance, recommended_action, evidence_refs and no extra keys. next_actions MUST be an array of strings. caveats MUST be an array of strings. evidence_refs MUST be an array and may only use BEFORE_RASTER, AFTER_RASTER, SITE_GEOMETRY, TEMPORAL_ANALYSIS. Keep the output concise and useful to a town planner."""
    input_text = ("GROUNDED TRACK B FACTS:\n" + json.dumps(facts, ensure_ascii=False, indent=2, default=str) + _numeric_allowlist_block(analysis))
    try:
        result, failures = generate_with_failover(instructions=instructions, input_text=input_text)
    except ProviderResilienceError as exc:
        raise TrackBAIError("No configured AI provider is currently available for Track B interpretation.") from exc
    payload = _parse_json(result.text)
    _canonicalize_list_fields(payload, string_fields=("next_actions", "caveats"), object_fields=("insights",))
    required = {"confidence", "executive_summary", "planner_problem", "insights", "next_actions", "caveats"}
    if set(payload) != required or payload.get("confidence") not in {"high", "moderate", "limited"}:
        raise TrackBAIError("AI provider returned a response outside the Track B interpretation contract.")
    if not isinstance(payload.get("insights"), list) or not isinstance(payload.get("next_actions"), list) or not isinstance(payload.get("caveats"), list):
        raise TrackBAIError("AI provider returned invalid Track B interpretation collections.")
    allowed_refs = {"BEFORE_RASTER", "AFTER_RASTER", "SITE_GEOMETRY", "TEMPORAL_ANALYSIS"}
    for insight in payload["insights"]:
        if not isinstance(insight, dict) or not {"title", "finding", "planning_relevance", "recommended_action", "evidence_refs"} <= set(insight):
            raise TrackBAIError("AI provider returned an invalid insight object.")
        if any(ref not in allowed_refs for ref in insight.get("evidence_refs", [])):
            raise TrackBAIError("AI provider referenced evidence outside the Track B evidence contract.")
    _validate_no_invented_numbers(payload, analysis)
    response = {
        "analysis_id": analysis_id, "provider": result.provider, "model": result.model,
        **payload, "evidence_policy": "provenance_controlled", "professional_review_required": True,
    }
    ai_path = path.parent / "ai_interpretation.json"
    ai_path.write_text(json.dumps(response, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
    return response


def _validate_comparison_numbers(payload: dict[str, Any], urban: dict[str, Any], rural: dict[str, Any]) -> None:
    allowed = _allowed_numeric_tokens(urban) | _allowed_numeric_tokens(rural)
    narrative = " ".join([
        str(payload.get("strategic_summary", "")), str(payload.get("urban_priority", "")),
        str(payload.get("rural_priority", "")), str(payload.get("shared_planning_problem", "")),
        *[str(x) for x in payload.get("priority_actions", [])], *[str(x) for x in payload.get("caveats", [])],
        *[str(i.get(k, "")) for i in payload.get("comparative_insights", []) for k in ("finding", "planning_relevance", "recommended_action")],
    ])
    narrative = _remove_leading_list_markers(narrative)
    for token in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", narrative):
        if token not in allowed:
            raise TrackBAIError(f"AI comparison introduced an ungrounded numeric claim: {token}")


def compare_track_b_urban_rural(*, project_id: uuid.UUID, urban_analysis_id: uuid.UUID, rural_analysis_id: uuid.UUID) -> dict[str, Any]:
    _, urban = _manifest(project_id, urban_analysis_id)
    _, rural = _manifest(project_id, rural_analysis_id)
    if urban.get("location_type") != "urban" or rural.get("location_type") != "rural":
        raise TrackBAIError("Urban-rural intelligence requires one analysis explicitly sourced from urban evidence and one from rural evidence.")
    for analysis in (urban, rural):
        evidence = analysis.get("evidence") or []
    if not evidence:
        raise TrackBAIError("AI operation requires an evidence payload with provenance.")

    def facts(a: dict[str, Any]) -> dict[str, Any]:
        return {k: a.get(k) for k in (
            "analysis_id", "location_type", "data_stage", "mode", "method", "before_datetime", "after_datetime",
            "usable_coverage_percent", "changed_pixel_count", "valid_pixel_count", "changed_percentage",
            "changed_area_hectares", "mean_before", "mean_after", "limitations", "evidence",
        )}

    instructions = """You are GeoPilot AI, a senior town-planning decision-support copilot. Compare only the supplied grounded urban and rural temporal evidence. Your job is not to describe imagery generically: identify how the measured evidence changes a planner's priorities, what should be investigated first in each context, what concern is shared, and what evidence-led actions should follow. Never invent measurements, causes, land-use classes, statutory rules, demographics, infrastructure facts, or external context. Do not assume a spectral change is development, degradation, deforestation, flooding, or non-compliance. Use conditional planning language and recommend verification where classification is not proven. NUMERIC GROUNDING RULE: every numeric token containing digits must be copied from one of the supplied deterministic facts or be a normal rounded display of that same fact. Never invent numbered steps, numeric ranks, action counts, zone counts, or numeric labels; use words instead of digits for non-measurement enumeration. Return JSON only with exactly: confidence (high|moderate|limited), strategic_summary, urban_priority, rural_priority, shared_planning_problem, comparative_insights, priority_actions, caveats. comparative_insights MUST be an array of objects containing exactly title, finding, planning_relevance, recommended_action, evidence_refs and no extra keys. priority_actions MUST be an array of strings. caveats MUST be an array of strings. evidence_refs MUST be an array and may only use URBAN_TEMPORAL_ANALYSIS, RURAL_TEMPORAL_ANALYSIS, URBAN_SITE_GEOMETRY, RURAL_SITE_GEOMETRY. Make the result useful to a professional town planner deciding where to inspect, compare, verify, or escalate review."""
    input_text = ("GROUNDED URBAN/RURAL FACTS:\n" + json.dumps({"urban": facts(urban), "rural": facts(rural)}, ensure_ascii=False, indent=2, default=str) + _numeric_allowlist_block(urban, rural))
    try:
        result, failures = generate_with_failover(instructions=instructions, input_text=input_text)
    except ProviderResilienceError as exc:
        raise TrackBAIError("No configured AI provider is currently available for Track B urban-rural comparison.") from exc
    payload = _parse_json(result.text)
    _canonicalize_list_fields(payload, string_fields=("priority_actions", "caveats"), object_fields=("comparative_insights",))
    required = {"confidence", "strategic_summary", "urban_priority", "rural_priority", "shared_planning_problem", "comparative_insights", "priority_actions", "caveats"}
    if set(payload) != required or payload.get("confidence") not in {"high", "moderate", "limited"}:
        raise TrackBAIError("AI provider returned a response outside the urban-rural comparison contract.")
    if not all(isinstance(payload.get(k), list) for k in ("comparative_insights", "priority_actions", "caveats")):
        raise TrackBAIError("AI provider returned invalid urban-rural comparison collections.")
    allowed_refs = {"URBAN_TEMPORAL_ANALYSIS", "RURAL_TEMPORAL_ANALYSIS", "URBAN_SITE_GEOMETRY", "RURAL_SITE_GEOMETRY"}
    for insight in payload["comparative_insights"]:
        if not isinstance(insight, dict) or not {"title", "finding", "planning_relevance", "recommended_action", "evidence_refs"} <= set(insight):
            raise TrackBAIError("AI provider returned an invalid comparative insight object.")
        if any(ref not in allowed_refs for ref in insight.get("evidence_refs", [])):
            raise TrackBAIError("AI provider referenced evidence outside the urban-rural comparison contract.")
    _validate_comparison_numbers(payload, urban, rural)
    return {"provider": result.provider, "model": result.model, **payload, "evidence_policy": "provenance_controlled", "professional_review_required": True}

_DECISION_REFS = {"BEFORE_RASTER", "AFTER_RASTER", "SITE_GEOMETRY", "TEMPORAL_ANALYSIS"}


def _validate_decision_numbers(payload: dict[str, Any], analysis: dict[str, Any]) -> None:
    allowed = _allowed_numeric_tokens(analysis)
    narrative = " ".join([
        str(payload.get("decision_title", "")),
        str(payload.get("issue", "")),
        str(payload.get("planning_implication", "")),
        str(payload.get("evidence_summary", "")),
        *[str(x) for x in payload.get("limitations", [])],
        *[str(item.get(k, "")) for item in payload.get("recommended_actions", []) for k in ("action", "rationale", "verification_needed")],
    ])
    narrative = _remove_leading_list_markers(narrative)
    for token in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", narrative):
        if token not in allowed:
            raise TrackBAIError(f"AI decision workspace introduced an ungrounded numeric claim: {token}")


def build_track_b_planner_decision(
    *,
    project_id: uuid.UUID,
    analysis_id: uuid.UUID,
    planner_question: str | None = None,
) -> dict[str, Any]:
    """Build a provenance-controlled planning decision packet from one temporal analysis.

    Priority is an AI triage label for planner attention only. It is explicitly not a
    statutory severity, compliance conclusion, development approval, or legal finding.
    """
    path, analysis = _manifest(project_id, analysis_id)
    evidence = analysis.get("evidence") or []
    if not evidence:
        raise TrackBAIError("AI operation requires an evidence payload with provenance.")

    question = (planner_question or "").strip() or None
    facts = {
        "analysis_id": str(analysis_id),
        "location_type": analysis.get("location_type"),
        "data_stage": analysis.get("data_stage"),
        "mode": analysis.get("mode"),
        "method": analysis.get("method"),
        "before_datetime": analysis.get("before_datetime"),
        "after_datetime": analysis.get("after_datetime"),
        "usable_coverage_percent": analysis.get("usable_coverage_percent"),
        "changed_pixel_count": analysis.get("changed_pixel_count"),
        "valid_pixel_count": analysis.get("valid_pixel_count"),
        "changed_percentage": analysis.get("changed_percentage"),
        "changed_area_hectares": analysis.get("changed_area_hectares"),
        "mean_before": analysis.get("mean_before"),
        "mean_after": analysis.get("mean_after"),
        "limitations": analysis.get("limitations") or [],
        "evidence": evidence,
        "planner_question": question,
    }
    instructions = """You are GeoPilot AI Decision Workspace, a senior town-planning copilot for PLAN-Ai Track B. Convert only the supplied grounded evidence into an auditable planner decision brief. If a planner question is supplied, answer it only to the extent supported by these facts. Never invent a measurement, cause, land-use class, demographic fact, infrastructure fact, statutory rule, external context, approval status, or location detail. Spectral/temporal change is evidence of measured change, not proof of development, deforestation, flooding, illegality, or non-compliance. priority is only a non-statutory TRIAGE label for planner attention: high, elevated, monitor, or evidence_limited. Use evidence_limited whenever data quality/coverage or the supplied evidence prevents a reliable planning implication. Every recommended action must be something a town planner can actually do next: inspect mapped change, compare organizer layers, conduct field verification, request professional review, or prioritize follow-up. NUMERIC GROUNDING RULE: every numeric token containing digits must be copied from a supplied deterministic fact or be a normal rounded display of that same fact. Never invent numbered steps, numeric ranks, action counts, zone counts, or numeric labels; use words instead of digits for non-measurement enumeration. Return JSON only with exactly these keys: confidence, priority, decision_title, issue, planning_implication, evidence_summary, recommended_actions, evidence_refs, limitations. confidence is high|moderate|limited. recommended_actions MUST be an array of objects containing exactly action, rationale, evidence_refs, verification_needed and no extra keys. evidence_refs MUST be an array of strings. limitations MUST be an array of strings. verification_needed MUST be a string. All evidence_refs may only be BEFORE_RASTER, AFTER_RASTER, SITE_GEOMETRY, TEMPORAL_ANALYSIS. Keep it concise, decision-oriented, and explicit about uncertainty."""
    input_text = ("GROUNDED TRACK B DECISION FACTS:\n" + json.dumps(facts, ensure_ascii=False, indent=2, default=str) + _numeric_allowlist_block(analysis))
    try:
        result, failures = generate_with_failover(instructions=instructions, input_text=input_text)
    except ProviderResilienceError as exc:
        raise TrackBAIError("No configured AI provider is currently available for the Track B planner decision workspace.") from exc

    payload = _parse_json(result.text)
    _canonicalize_list_fields(payload, string_fields=("evidence_refs", "limitations"), object_fields=("recommended_actions",))
    required = {"confidence", "priority", "decision_title", "issue", "planning_implication", "evidence_summary", "recommended_actions", "evidence_refs", "limitations"}
    if set(payload) != required:
        raise TrackBAIError("AI provider returned a response outside the planner decision workspace contract.")
    if payload.get("confidence") not in {"high", "moderate", "limited"} or payload.get("priority") not in {"high", "elevated", "monitor", "evidence_limited"}:
        raise TrackBAIError("AI provider returned an invalid planner confidence or triage priority.")
    if not isinstance(payload.get("recommended_actions"), list) or not isinstance(payload.get("evidence_refs"), list) or not isinstance(payload.get("limitations"), list):
        raise TrackBAIError("AI provider returned invalid planner decision collections.")
    if any(ref not in _DECISION_REFS for ref in payload.get("evidence_refs", [])):
        raise TrackBAIError("AI provider referenced evidence outside the planner decision contract.")
    for action in payload["recommended_actions"]:
        if not isinstance(action, dict) or set(action) != {"action", "rationale", "evidence_refs", "verification_needed"}:
            raise TrackBAIError("AI provider returned an invalid planner action object.")
        if not isinstance(action.get("evidence_refs"), list) or any(ref not in _DECISION_REFS for ref in action.get("evidence_refs", [])):
            raise TrackBAIError("AI planner action referenced evidence outside the Track B evidence contract.")

    _validate_decision_numbers(payload, analysis)
    response = {
        "analysis_id": analysis_id,
        "provider": result.provider,
        "model": result.model,
        **payload,
        "planner_question": question,
        "evidence_policy": "provenance_controlled",
        "professional_review_required": True,
    }
    decision_path = path.parent / "planner_decision.json"
    decision_path.write_text(json.dumps(response, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
    return response

# TRACKB_TERRAIN_DECISION_ROUTER_V2
def _terrain_numeric_allowlist(facts: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for value in facts.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            allowed.add(str(value))
            for places in range(0, 9):
                allowed.add(f"{float(value):.{places}f}")
    return allowed


def _validate_terrain_decision_numbers(payload: dict[str, Any], facts: dict[str, Any]) -> None:
    allowed = _terrain_numeric_allowlist(facts)
    narrative = " ".join([
        str(payload.get("decision_title", "")),
        str(payload.get("issue", "")),
        str(payload.get("planning_implication", "")),
        str(payload.get("evidence_summary", "")),
        *[str(x) for x in payload.get("limitations", [])],
        *[
            str(item.get(k, ""))
            for item in payload.get("recommended_actions", [])
            for k in ("action", "rationale", "verification_needed")
        ],
    ])
    narrative = _remove_leading_list_markers(narrative)
    for token in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", narrative):
        if token not in allowed:
            raise TrackBAIError(f"Terrain decision introduced an ungrounded numeric claim: {token}")


def build_track_b_terrain_planner_decision(
    *,
    session,
    owner,
    project_id: uuid.UUID,
    analysis_id: uuid.UUID,
    planner_question: str,
) -> dict[str, Any]:
    from app.services.terrain_analysis import calculate_site_terrain_summary

    path, analysis = _manifest(project_id, analysis_id)
    raw_site_id = analysis.get("site_id")
    if not raw_site_id:
        raise TrackBAIError("Terrain question cannot be executed because the Track B analysis has no Site.")

    try:
        site_id = uuid.UUID(str(raw_site_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise TrackBAIError("Track B analysis contains an invalid Site identifier.") from exc

    summary = calculate_site_terrain_summary(
        session,
        owner=owner,
        project_id=project_id,
        site_id=site_id,
    )

    facts = {
        "valid_pixel_count": summary.valid_pixel_count,
        "elevation_min_m": summary.elevation_min_m,
        "elevation_max_m": summary.elevation_max_m,
        "elevation_mean_m": summary.elevation_mean_m,
        "slope_min_degrees": summary.slope_min_degrees,
        "slope_max_degrees": summary.slope_max_degrees,
        "slope_mean_degrees": summary.slope_mean_degrees,
        "max_slope_longitude": summary.max_slope_longitude,
        "max_slope_latitude": summary.max_slope_latitude,
        "crs": summary.crs,
        "raster_checksum_sha256": summary.raster_checksum_sha256,
        "source_uri": summary.source_uri,
    }

    instructions = (
        "You are GeoPilot AI Decision Workspace. Answer the planner's TERRAIN MEASUREMENT "
        "question using ONLY the supplied deterministic terrain facts from terrain.site_summary. "
        "Do not use NDVI, temporal change, basemap appearance, or general knowledge to invent "
        "terrain measurements. If the question asks for highest or maximum slope, answer from "
        "slope_max_degrees. If it asks for maximum elevation, answer from elevation_max_m. "
        "Clearly state the unit. Numeric claims must be copied from supplied terrain facts or "
        "normally rounded from those same facts. Return JSON only with exactly these keys: "
        "confidence, priority, decision_title, issue, planning_implication, evidence_summary, "
        "recommended_actions, evidence_refs, limitations. confidence must be high|moderate|limited. "
        "priority must be high|elevated|monitor|evidence_limited and is non-statutory planner "
        "triage only. recommended_actions must be an array of objects with exactly action, "
        "rationale, evidence_refs, verification_needed. evidence_refs must only contain "
        "TERRAIN_SITE_SUMMARY. limitations must be an array of strings. Keep the direct answer "
        "prominent and concise."
    )

    allowed = sorted(_terrain_numeric_allowlist(facts), key=lambda x: (len(x), x))
    input_text = (
        "PLANNER QUESTION:\n" + planner_question.strip()
        + "\n\nDETERMINISTIC TERRAIN FACTS:\n"
        + json.dumps(facts, ensure_ascii=False, indent=2, default=str)
        + "\n\nALLOWED NUMERIC TOKENS:\n"
        + ", ".join(allowed)
    )

    try:
        result, failures = generate_with_failover(
            instructions=instructions,
            input_text=input_text,
        )
    except ProviderResilienceError as exc:
        raise TrackBAIError("No configured AI provider is currently available for terrain synthesis.") from exc

    payload = _parse_json(result.text)
    _canonicalize_list_fields(
        payload,
        string_fields=("evidence_refs", "limitations"),
        object_fields=("recommended_actions",),
    )

    required = {
        "confidence", "priority", "decision_title", "issue",
        "planning_implication", "evidence_summary",
        "recommended_actions", "evidence_refs", "limitations",
    }
    if set(payload) != required:
        raise TrackBAIError("AI provider returned a response outside the terrain decision contract.")

    if payload.get("confidence") not in {"high", "moderate", "limited"}:
        raise TrackBAIError("AI provider returned an invalid terrain confidence.")

    if payload.get("priority") not in {"high", "elevated", "monitor", "evidence_limited"}:
        raise TrackBAIError("AI provider returned an invalid terrain triage priority.")

    refs = payload.get("evidence_refs", [])
    if not isinstance(refs, list) or any(ref != "TERRAIN_SITE_SUMMARY" for ref in refs):
        raise TrackBAIError("Terrain synthesis referenced evidence outside terrain.site_summary.")

    actions = payload.get("recommended_actions", [])
    if not isinstance(actions, list):
        raise TrackBAIError("AI provider returned invalid terrain actions.")

    for action in actions:
        if not isinstance(action, dict) or set(action) != {
            "action", "rationale", "evidence_refs", "verification_needed"
        }:
            raise TrackBAIError("AI provider returned an invalid terrain action object.")
        action_refs = action.get("evidence_refs", [])
        if not isinstance(action_refs, list) or any(
            ref != "TERRAIN_SITE_SUMMARY" for ref in action_refs
        ):
            raise TrackBAIError("Terrain action referenced evidence outside terrain.site_summary.")

    _validate_terrain_decision_numbers(payload, facts)

    response = {
        "analysis_id": analysis_id,
        "provider": result.provider,
        "model": result.model,
        **payload,
        "planner_question": planner_question.strip(),
        "evidence_policy": "project_site_terrain_evidence",
        "professional_review_required": True,
    }

    terrain_path = path.parent / "planner_decision_terrain.json"
    terrain_path.write_text(
        json.dumps(response, default=str, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return response


