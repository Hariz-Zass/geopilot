from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

from app.schemas.tool_evidence import ToolEvidence


class GroundingError(Exception):
    pass


BANNED = (
    r"\bplanning permission (?:is|has been) granted\b",
    r"\bstatutorily approved\b",
    r"\blegally compliant\b",
)


NUMERIC_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
)


def evidence_context(
    items: list[ToolEvidence],
) -> str:
    return json.dumps(
        [
            item.model_dump(mode="json")
            for item in items
        ],
        sort_keys=True,
        default=str,
    )


def _canonical_number(
    value: str,
) -> str:
    cleaned = value.replace(",", "").strip()

    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return cleaned

    if number == number.to_integral():
        return str(number.quantize(Decimal("1")))

    normalized = format(number.normalize(), "f")

    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")

    return normalized


def _add_numeric_token(
    tokens: set[str],
    value: str,
) -> None:
    cleaned = value.replace(",", "").strip()

    if not cleaned:
        return

    tokens.add(cleaned)
    tokens.add(_canonical_number(cleaned))


def _payload_numeric_tokens(
    items: list[ToolEvidence],
) -> set[str]:
    tokens: set[str] = set()

    def walk(value) -> None:
        if value is None or isinstance(value, bool):
            return

        if isinstance(value, (int, float, Decimal)):
            raw = str(value)
            _add_numeric_token(
                tokens,
                raw,
            )
            return

        if isinstance(value, str):
            for match in NUMERIC_PATTERN.findall(
                value
            ):
                _add_numeric_token(
                    tokens,
                    match,
                )
            return

        if isinstance(value, dict):
            for nested in value.values():
                walk(nested)
            return

        if isinstance(value, (list, tuple, set)):
            for nested in value:
                walk(nested)

    for item in items:
        walk(item.payload)

    return tokens


def validate_synthesis(
    text: str,
    evidence: list[ToolEvidence],
) -> str:
    cleaned_text = text.strip()
    low = cleaned_text.casefold()

    for pattern in BANNED:
        if re.search(
            pattern,
            low,
        ):
            raise GroundingError(
                "Synthesis contains prohibited "
                "statutory/approval wording."
            )

    # Every numeric claim in the synthesis must exist somewhere
    # inside the validated ToolEvidence payload.
    #
    # This includes numbers embedded in retrieved document text,
    # such as publication years, density ranges, percentages,
    # page-related values, distances and other numeric evidence.
    allowed = _payload_numeric_tokens(
        evidence
    )

    numeric_claims = NUMERIC_PATTERN.findall(
        cleaned_text
    )

    for claim in numeric_claims:
        canonical_claim = _canonical_number(
            claim
        )

        if canonical_claim not in allowed:
            # Permit ordinary decimal rounding of an evidence
            # number, while continuing to reject invented values.
            #
            # Example:
            # evidence: 98.93591040458347
            # synthesis: 98.94
            rounded_match = False

            try:
                claim_decimal = Decimal(
                    claim.replace(",", "")
                )

                if "." in claim:
                    decimal_places = len(
                        claim.split(".", 1)[1]
                    )

                    quantum = Decimal(1).scaleb(
                        -decimal_places
                    )

                    for token in allowed:
                        try:
                            evidence_decimal = Decimal(
                                token
                            )
                        except InvalidOperation:
                            continue

                        if (
                            evidence_decimal.quantize(
                                quantum
                            )
                            == claim_decimal
                        ):
                            rounded_match = True
                            break

            except InvalidOperation:
                rounded_match = False

            if not rounded_match:
                raise GroundingError(
                    f"Unsupported numeric claim: {claim}"
                )

    return cleaned_text