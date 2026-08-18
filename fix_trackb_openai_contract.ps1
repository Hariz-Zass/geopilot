$ErrorActionPreference = 'Stop'

$root = (Get-Location).Path
$aiPath = Join-Path $root 'backend\app\services\track_b_ai.py'
$testPath = Join-Path $root 'backend\tests\test_track_b_hackathon.py'

if (!(Test-Path $aiPath) -or !(Test-Path $testPath)) {
    throw 'Run this from the geopilot_v7 project root.'
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $root ("artifacts\trackb_contract_backup_" + $stamp)
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item $aiPath (Join-Path $backupDir 'track_b_ai.py')
Copy-Item $testPath (Join-Path $backupDir 'test_track_b_hackathon.py')
Write-Host "BACKUP: $backupDir"

$text = Get-Content $aiPath -Raw
$marker = '# TRACKB_OPENAI_CONTRACT_PATCH_V1'

if ($text -notmatch [regex]::Escape($marker)) {
    $old = '            values.add(f"{float(value):.4f}")'
    $new = @'
            values.add(f"{float(value):.4f}")
            values.add(f"{float(value):.5f}")
            values.add(f"{float(value):.6f}")
            values.add(f"{float(value):.7f}")
            values.add(f"{float(value):.8f}")
'@
    if (-not $text.Contains($old)) { throw 'Numeric formatting marker not found.' }
    $text = $text.Replace($old, $new.TrimEnd())

    $old = @'
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
'@
    $new = $old + @'

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
'@
    if (-not $text.Contains($old)) { throw 'JSON parser marker not found.' }
    $text = $text.Replace($old, $new)

    $needle = '    for token in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", narrative):'
    $replacement = @'
    narrative = _remove_leading_list_markers(narrative)
    for token in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", narrative):
'@
    $count = ([regex]::Matches($text, [regex]::Escape($needle))).Count
    if ($count -ne 3) { throw "Expected 3 numeric validator loops, found $count." }
    $text = $text.Replace($needle, $replacement.TrimEnd())

    $old = 'Do not issue planning approval, legal certification, or statutory conclusions. Return JSON only with exactly these keys: confidence (high|moderate|limited), executive_summary, planner_problem, insights, next_actions, caveats. insights is an array of objects with title, finding, planning_relevance, recommended_action, evidence_refs. evidence_refs may only use BEFORE_RASTER, AFTER_RASTER, SITE_GEOMETRY, TEMPORAL_ANALYSIS. Keep the output concise and useful to a town planner.'
    $new = 'Do not issue planning approval, legal certification, or statutory conclusions. NUMERIC GROUNDING RULE: every numeric token containing digits must be copied from a supplied deterministic fact or be a normal rounded display of that same fact. Never invent numbered steps, numeric ranks, action counts, zone counts, or numeric labels; use words instead of digits for non-measurement enumeration. Return JSON only with exactly these keys: confidence (high|moderate|limited), executive_summary, planner_problem, insights, next_actions, caveats. insights MUST be an array of objects containing exactly title, finding, planning_relevance, recommended_action, evidence_refs and no extra keys. next_actions MUST be an array of strings. caveats MUST be an array of strings. evidence_refs MUST be an array and may only use BEFORE_RASTER, AFTER_RASTER, SITE_GEOMETRY, TEMPORAL_ANALYSIS. Keep the output concise and useful to a town planner.'
    if (-not $text.Contains($old)) { throw 'Interpretation prompt marker not found.' }
    $text = $text.Replace($old, $new)

    $old = 'Return JSON only with exactly: confidence (high|moderate|limited), strategic_summary, urban_priority, rural_priority, shared_planning_problem, comparative_insights, priority_actions, caveats. comparative_insights is an array of objects with title, finding, planning_relevance, recommended_action, evidence_refs. evidence_refs may only use URBAN_TEMPORAL_ANALYSIS, RURAL_TEMPORAL_ANALYSIS, URBAN_SITE_GEOMETRY, RURAL_SITE_GEOMETRY. Make the result useful to a professional town planner deciding where to inspect, compare, verify, or escalate review.'
    $new = 'NUMERIC GROUNDING RULE: every numeric token containing digits must be copied from one of the supplied deterministic facts or be a normal rounded display of that same fact. Never invent numbered steps, numeric ranks, action counts, zone counts, or numeric labels; use words instead of digits for non-measurement enumeration. Return JSON only with exactly: confidence (high|moderate|limited), strategic_summary, urban_priority, rural_priority, shared_planning_problem, comparative_insights, priority_actions, caveats. comparative_insights MUST be an array of objects containing exactly title, finding, planning_relevance, recommended_action, evidence_refs and no extra keys. priority_actions MUST be an array of strings. caveats MUST be an array of strings. evidence_refs MUST be an array and may only use URBAN_TEMPORAL_ANALYSIS, RURAL_TEMPORAL_ANALYSIS, URBAN_SITE_GEOMETRY, RURAL_SITE_GEOMETRY. Make the result useful to a professional town planner deciding where to inspect, compare, verify, or escalate review.'
    if (-not $text.Contains($old)) { throw 'Comparison prompt marker not found.' }
    $text = $text.Replace($old, $new)

    $old = 'Return JSON only with exactly these keys: confidence, priority, decision_title, issue, planning_implication, evidence_summary, recommended_actions, evidence_refs, limitations. confidence is high|moderate|limited. recommended_actions is an array of objects with exactly action, rationale, evidence_refs, verification_needed. All evidence_refs may only be BEFORE_RASTER, AFTER_RASTER, SITE_GEOMETRY, TEMPORAL_ANALYSIS. Keep it concise, decision-oriented, and explicit about uncertainty.'
    $new = 'NUMERIC GROUNDING RULE: every numeric token containing digits must be copied from a supplied deterministic fact or be a normal rounded display of that same fact. Never invent numbered steps, numeric ranks, action counts, zone counts, or numeric labels; use words instead of digits for non-measurement enumeration. Return JSON only with exactly these keys: confidence, priority, decision_title, issue, planning_implication, evidence_summary, recommended_actions, evidence_refs, limitations. confidence is high|moderate|limited. recommended_actions MUST be an array of objects containing exactly action, rationale, evidence_refs, verification_needed and no extra keys. evidence_refs MUST be an array of strings. limitations MUST be an array of strings. verification_needed MUST be a string. All evidence_refs may only be BEFORE_RASTER, AFTER_RASTER, SITE_GEOMETRY, TEMPORAL_ANALYSIS. Keep it concise, decision-oriented, and explicit about uncertainty.'
    if (-not $text.Contains($old)) { throw 'Decision prompt marker not found.' }
    $text = $text.Replace($old, $new)

    $old = @'
    payload = _parse_json(result.text)
    required = {"confidence", "executive_summary", "planner_problem", "insights", "next_actions", "caveats"}
'@
    $new = @'
    payload = _parse_json(result.text)
    _canonicalize_list_fields(payload, string_fields=("next_actions", "caveats"), object_fields=("insights",))
    required = {"confidence", "executive_summary", "planner_problem", "insights", "next_actions", "caveats"}
'@
    if (-not $text.Contains($old)) { throw 'Interpretation parse marker not found.' }
    $text = $text.Replace($old, $new)

    $old = @'
    payload = _parse_json(result.text)
    required = {"confidence", "strategic_summary", "urban_priority", "rural_priority", "shared_planning_problem", "comparative_insights", "priority_actions", "caveats"}
'@
    $new = @'
    payload = _parse_json(result.text)
    _canonicalize_list_fields(payload, string_fields=("priority_actions", "caveats"), object_fields=("comparative_insights",))
    required = {"confidence", "strategic_summary", "urban_priority", "rural_priority", "shared_planning_problem", "comparative_insights", "priority_actions", "caveats"}
'@
    if (-not $text.Contains($old)) { throw 'Comparison parse marker not found.' }
    $text = $text.Replace($old, $new)

    $old = @'
    payload = _parse_json(result.text)
    required = {"confidence", "priority", "decision_title", "issue", "planning_implication", "evidence_summary", "recommended_actions", "evidence_refs", "limitations"}
'@
    $new = @'
    payload = _parse_json(result.text)
    _canonicalize_list_fields(payload, string_fields=("evidence_refs", "limitations"), object_fields=("recommended_actions",))
    required = {"confidence", "priority", "decision_title", "issue", "planning_implication", "evidence_summary", "recommended_actions", "evidence_refs", "limitations"}
'@
    if (-not $text.Contains($old)) { throw 'Decision parse marker not found.' }
    $text = $text.Replace($old, $new)

    Set-Content -Path $aiPath -Value $text -Encoding UTF8
    Write-Host 'PATCHED track_b_ai.py'
} else {
    Write-Host 'Patch already present; source patch skipped.'
}

$tests = Get-Content $testPath -Raw
if ($tests -notmatch 'test_track_b_openai_contract_accepts_grounded_rounding_and_list_markers') {
$tests += @'


def test_track_b_openai_contract_accepts_grounded_rounding_and_list_markers():
    from app.services.track_b_ai import _validate_no_invented_numbers
    analysis = {
        "changed_percentage": 12.5, "changed_area_hectares": 4.2,
        "usable_coverage_percent": 95.0, "changed_pixel_count": 125,
        "valid_pixel_count": 1000, "mean_before": 0.469983, "mean_after": 0.401234,
        "before_datetime": "2026-01-01T00:00:00Z", "after_datetime": "2026-06-01T00:00:00Z",
    }
    payload = {
        "executive_summary": "Measured mean before is 0.46998.",
        "planner_problem": "Review measured change.", "insights": [],
        "next_actions": ["1. Inspect mapped change.", "2) Compare organizer evidence."], "caveats": [],
    }
    _validate_no_invented_numbers(payload, analysis)


def test_track_b_openai_contract_still_rejects_nonlist_numeric_claim():
    import pytest
    from app.services.track_b_ai import TrackBAIError, _validate_no_invented_numbers
    analysis = {
        "changed_percentage": 12.5, "changed_area_hectares": 4.2,
        "usable_coverage_percent": 95.0, "changed_pixel_count": 125,
        "valid_pixel_count": 1000, "mean_before": 0.469983, "mean_after": 0.401234,
        "before_datetime": "2026-01-01T00:00:00Z", "after_datetime": "2026-06-01T00:00:00Z",
    }
    payload = {
        "executive_summary": "Measured change is 12.50%.",
        "planner_problem": "Review measured change.", "insights": [],
        "next_actions": ["Inspect 2 unsupported priority zones."], "caveats": [],
    }
    with pytest.raises(TrackBAIError):
        _validate_no_invented_numbers(payload, analysis)


def test_track_b_openai_contract_canonicalizes_harmless_collection_shape_drift():
    from app.services.track_b_ai import _canonicalize_list_fields
    payload = {
        "priority_actions": "Inspect mapped change.", "caveats": None,
        "comparative_insights": {
            "title": "Review", "finding": "Measured change requires verification.",
            "planning_relevance": "Prioritize review.", "recommended_action": "Inspect mapped change.",
            "evidence_refs": ["URBAN_TEMPORAL_ANALYSIS"],
        },
    }
    _canonicalize_list_fields(payload, string_fields=("priority_actions", "caveats"), object_fields=("comparative_insights",))
    assert payload["priority_actions"] == ["Inspect mapped change."]
    assert payload["caveats"] == []
    assert isinstance(payload["comparative_insights"], list)
'@
    Set-Content -Path $testPath -Value $tests -Encoding UTF8
    Write-Host 'APPENDED regression tests'
}

Write-Host 'PATCH STEP COMPLETE'
