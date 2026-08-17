# ADR-0001 — Clean-room rebuild

## Decision
Rebuild GeoPilot AI from zero. Historical source code, database state, migrations, fixtures, IDs, and evidence are not imported.

## Rationale
The Master Developer Handover is used as the authoritative product/architecture specification while avoiding legacy implementation debt and runtime-state ambiguity.

## Consequences
- Alembic begins at 0001.
- Acceptance data will be newly created and explicitly classified as test, controlled-real, or production/demo evidence.
- Historical task status informs target capability but does not confer acceptance on the new implementation.
