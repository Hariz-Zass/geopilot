# ADR-0004 — Controlled document acquisition

## Decision
Support both owner/user document upload and controlled external document acquisition/import.

## Rules
- External acquisition uses explicit source adapters or allowlists, not arbitrary Planning Officer URL fetching.
- Every imported document receives immutable source/version/provenance metadata.
- Retrieval evidence is not automatically verified policy.
- Human review is required before candidate policy evidence is promoted to verified policy representation.
