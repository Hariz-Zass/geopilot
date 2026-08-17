# TASK-010 — Project/Site Isolation Gate

## Status
PASS

## Objective
Establish one reusable, fail-closed authorization/state boundary before GeoPilot begins adding map, document, GIS, raster, compliance, suitability, or AI evidence domains.

## Scope delivered
- Central `resolve_project_scope` ownership resolver.
- Central `resolve_site_scope` resolver that requires both the authorized parent `project_id` and exact `site_id`.
- Canonical `resolve_analysis_scope` for evidence-producing analysis.
- Explicit project states: `ANY`, `ACTIVE`.
- Explicit site states: `ANY`, `AVAILABLE`, `ACTIVE`.
- FastAPI `get_analysis_scope` dependency for future analytical routes.
- Existing Project/Site service access refactored through the centralized isolation boundary while preserving public API behavior.
- Adversarial regression coverage for ID substitution and archived/inactive contexts.

## Security/integrity contract
1. Project resolution is always scoped by authenticated `owner_id`.
2. A foreign-owned Project is indistinguishable from a missing Project.
3. Site resolution happens only after Project ownership is established.
4. A Site query always binds `site_id` and the already-authorized `project_id` together.
5. A Site ID from Project A must not resolve under Project B, even if both Projects have the same owner.
6. Audit/read CRUD may explicitly resolve archived resources when required.
7. Evidence-producing analysis must reject archived Projects, archived Sites, and inactive Sites.
8. State rejection happens only after ownership/scope identity has been verified, avoiding cross-owner state disclosure.
9. Future evidence-producing domains must enter through `resolve_analysis_scope` or a stricter domain-specific derivative.

## Persistence
No migration was introduced. Alembic head remains `0004`.

## Acceptance evidence
- Full backend regression suite: 63 passed.
- New isolation adversarial tests: 9 passed as part of the full suite.
- No new domain tables.
- No Git commit created.

## Deferred runtime gates
- Live PostgreSQL/PostGIS execution remains pending on the owner's Docker runtime.
- Frontend dependency-backed TASK-005 gates remain pending from the npm-registry limitation in the ChatGPT runtime.

## Explicit non-scope
- MapLibre implementation.
- GISLayer/GISFeature.
- Planning-document persistence.
- Compliance/Suitability.
- Raster/satellite processing.
- Planning Officer/tool execution.
