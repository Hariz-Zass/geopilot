# TASK-023 — PolicyReference Workflow

Status: PASS

## Scope
Build the reviewed, project-scoped PolicyReference workflow that sits between validated document citations and future deterministic PolicyCriterion/Compliance use.

## Implemented contract
- A PolicyReference can only be created from a validated `document_citation.v1` reference.
- Source wording is copied server-side from the validated persisted chunk; clients cannot supply or replace authoritative source wording.
- Exact Project → Document → Version → Page → Chunk identities and version/page/chunk SHA-256 identities are persisted.
- New references always start as `representation_state=draft`, `review_state=unreviewed`, `applicability_status=unassessed`.
- Explicit human review actions are separated from candidate creation: `verify`, `reject`, `requires_review`.
- Only `final + verified + non-archived` records can resolve for downstream policy-evidence use.
- Verification re-resolves and revalidates the current citation source before promotion.
- Final PolicyReference content is immutable; only archive state may change after finalization.
- Rejected references remain durable audit records but can never resolve for downstream evidence use.
- Applicability remains a separate reviewed dimension and can remain unassessed even when the source-grounded interpretation is verified.
- Downstream resolution always carries explicit limitations that verification is not statutory approval, legal certification, planning permission, or automatic site applicability.

## Persistence
Migration `0011_policy_reference_workflow` creates `policy_references` with exact source foreign keys, source snapshots/hashes, author/reviewer identities, draft/final state, review state, applicability state and consistency constraints.

## API
- `POST /api/v1/projects/{project_id}/policy-references`
- `GET /api/v1/projects/{project_id}/policy-references`
- `GET /api/v1/projects/{project_id}/policy-references/{policy_reference_id}`
- `PATCH /api/v1/projects/{project_id}/policy-references/{policy_reference_id}`
- `POST /api/v1/projects/{project_id}/policy-references/{policy_reference_id}/review`
- `POST /api/v1/projects/{project_id}/policy-references/{policy_reference_id}/resolve`

## Acceptance
- Focused PolicyReference + Citation + migration tests: 25/25 PASS.
- Full backend regression: 195/195 PASS, executed as 100/100 + 95/95 split.
- Python compile gate: PASS.
- Alembic single head: `0011`.
- Offline PostgreSQL upgrade `0010 → 0011`: PASS.
- Offline downgrade `0011 → 0010`: PASS.
- No Git commit created.

## Explicit non-scope
- PolicyCriterion is not introduced; TASK-024 owns deterministic criterion representation.
- Compliance execution is not introduced.
- AI-generated policy truth is not introduced.
