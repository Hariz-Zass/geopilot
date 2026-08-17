# TASK-016 — MapAction Service

## Status
PASS

## Objective
Introduce typed map instructions that can drive the frontend only through validated `GeometryReference` objects and server-resolved geometry.

## Contract
- MapAction v1 supports `focus`, `fit`, and `highlight`.
- `focus` requires exactly one GeometryReference.
- `fit` and `highlight` accept one or more unique GeometryReferences (maximum 100).
- MapAction contains no authoritative client geometry payload.
- Every reference must belong to the exact authenticated project path and must resolve through the canonical TASK-015 GeometryReference resolver.
- Resolution is all-or-nothing: stale, unavailable, missing, cross-project, or malformed references fail closed; no geometry is silently skipped.
- Resolved geometry preserves input reference ordering and is explicitly labelled `server_resolved`.
- No database persistence or migration is introduced in TASK-016.

## API
`POST /api/v1/projects/{project_id}/map-actions/resolve`

## Prohibited scope
MapAction persistence, PlanningRun, findings, ToolEvidence, AI tool execution, arbitrary client geometry, and frontend authoritative calculations are not part of TASK-016.
