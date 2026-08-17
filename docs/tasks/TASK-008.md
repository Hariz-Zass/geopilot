# TASK-008 — Project Domain

## Objective
Introduce `Project` as the top-level authenticated isolation boundary. Every project operation must be scoped to the current authenticated owner, and cross-owner resource existence must not leak through the API.

## Implemented
- `Project` ORM entity with UUID identity, required `owner_id`, normalized name, optional description, archive state and timestamps.
- Ownership foreign key from `projects.owner_id` to `users.id` with `ON DELETE CASCADE`.
- Alembic revision `0003_project_domain`, following `0002_user_auth`.
- Authenticated project endpoints:
  - `POST /api/v1/projects`
  - `GET /api/v1/projects`
  - `GET /api/v1/projects/{project_id}`
  - `PATCH /api/v1/projects/{project_id}`
  - `DELETE /api/v1/projects/{project_id}`
- Owner-scoped service functions for create, list, get, update and delete.
- Default list excludes archived projects; `include_archived=true` exposes them to their owner for audit/review.
- Cross-owner get/update/delete uses the same `project_not_found` 404 contract as a missing UUID.
- Project names and descriptions are normalized at the API boundary.

## Hard-gate defect discovered and repaired
TASK-008 exposed a generic error-contract defect: Pydantic custom validation errors may include a Python `ValueError` object under `ctx`, which the previous centralized validation handler attempted to place directly in JSON. The handler now uses FastAPI JSON encoding with an explicit `ValueError -> str` encoder so domain validation returns a stable 422 instead of a 500. Regression coverage was added through the blank-project-name case.

## Isolation boundaries
- Authentication is mandatory for every Project route.
- Every Project query contains the current user's owner identity.
- A caller cannot discover whether a project UUID belongs to another user through get, patch or delete behavior.
- Archived projects remain owner-scoped and are never returned to another user.
- Site/domain-child isolation is not claimed yet; Site begins in TASK-009.

## Acceptance
- Full backend suite: 37/37 PASS.
- Alembic single head: `0003`.
- Offline upgrade sequence: `0001 -> 0002 -> 0003` PASS.
- Offline SQL creates `projects` with an owner foreign key to `users` and does not create `sites`.
- SQLAlchemy metadata contains exactly `users` and `projects` application tables.
- Cross-owner CRUD regression tests PASS.
- Archive filtering regression tests PASS.
- Validation-error serialization regression test PASS.
- Git commit count remains 0.
- Live PostgreSQL/Docker migration remains a local-runtime gate because this ChatGPT runtime has no Docker daemon.
