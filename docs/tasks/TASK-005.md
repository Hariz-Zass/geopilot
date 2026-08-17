# TASK-005 — Frontend React/TypeScript Foundation

## Goal
Establish a maintainable browser application foundation before planning-domain UI begins.

## Acceptance contract
1. React/TypeScript application starts through Vite.
2. Routes are server-independent browser routes with an explicit not-found state.
3. API base URL is typed and validated.
4. Backend failures use a stable frontend error type and preserve request IDs where provided.
5. At least loading, success and error states exist for a real backend readiness call.
6. Unit/component testing, linting, typecheck and production build commands are defined.
7. No Project/Site, map, AI or planning-domain implementation is introduced.

## Environment note
The implementation was statically audited in the ChatGPT build environment. npm package retrieval timed out before dependencies could be installed, so dependency-backed quality commands must be executed on a network-capable runtime before this task receives runtime acceptance.
