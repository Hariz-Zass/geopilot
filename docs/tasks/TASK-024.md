# TASK-024 — PolicyCriterion Domain

Status: PASS

## Scope
Build reviewed, project-scoped deterministic policy-rule representations from verified PolicyReference evidence without allowing arbitrary or fabricated thresholds.

## Implemented contract
- A PolicyCriterion can only be created from a `final + verified + non-archived` PolicyReference that itself still resolves against its exact source citation.
- Criterion creation never promotes retrieval text directly into a deterministic rule.
- Supported value types: `numeric`, `text`, `boolean`, `set`, and `manual_review`.
- Supported operators are typed and value-type constrained: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `between`, `in`, `not_in`, `bool_eq`, and `manual_review`.
- Numeric thresholds/range bounds must be explicitly present in the exact `source_evidence_text` passage copied from the verified PolicyReference source wording. A source that states `60` cannot silently produce a criterion threshold of `70`.
- Text/set expected values must also appear explicitly in the source evidence passage.
- Boolean criteria require interpretation notes because boolean policy meaning is interpretive rather than inferred automatically.
- New criteria begin as `draft + unreviewed`; explicit review actions are `verify`, `reject`, and `requires_review`.
- Verification re-resolves the parent PolicyReference and re-runs source-grounding checks before finalization.
- Only `final + verified + non-archived` criteria can resolve for future deterministic engines.
- Final criterion content is immutable; only archive state may change after finalization.
- Criterion codes are unique within a project.
- Resolution carries explicit limitations that a reviewed deterministic rule is not statutory approval, legal certification, or automatic site applicability.

## Persistence
Migration `0012_policy_criterion_domain` creates `policy_criteria` with:
- exact project and PolicyReference foreign keys;
- author/reviewer identities;
- typed value/operator fields;
- numeric/text/boolean/set payload fields;
- source-evidence passage and interpretation/applicability notes;
- review/final/archive state;
- project-local unique criterion code;
- database check constraints for state, operator/type compatibility, range validity and payload shape.

## API
- `POST /api/v1/projects/{project_id}/policy-criteria`
- `GET /api/v1/projects/{project_id}/policy-criteria`
- `GET /api/v1/projects/{project_id}/policy-criteria/{criterion_id}`
- `PATCH /api/v1/projects/{project_id}/policy-criteria/{criterion_id}`
- `POST /api/v1/projects/{project_id}/policy-criteria/{criterion_id}/review`
- `POST /api/v1/projects/{project_id}/policy-criteria/{criterion_id}/resolve`

## Acceptance
- Focused TASK-024 tests: 11/11 PASS.
- Full backend regression: 206/206 PASS, executed as 108/108 + 98/98 split to avoid environment timeout.
- Python compile gate: PASS.
- Alembic single head: `0012`.
- Offline PostgreSQL upgrade `0011 → 0012`: PASS.
- Offline downgrade `0012 → 0011`: PASS.
- No Git commit created.

## Explicit non-scope
- ComplianceFact is not introduced; TASK-025 owns persisted site/project evidence facts.
- Compliance execution is not introduced; TASK-026 owns deterministic operator evaluation.
- The Planning Officer is not allowed to invent thresholds or create policy truth.
