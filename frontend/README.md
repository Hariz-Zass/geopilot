# GeoPilot AI Frontend Foundation

TASK-005 establishes the frontend application boundary only.

## Included
- React + TypeScript + Vite application shell.
- React Router route tree.
- Typed `VITE_*` configuration validation.
- Fetch-based API client with GeoPilot backend error mapping and request-ID propagation.
- Explicit loading, ready and error UI states.
- Vitest/jsdom + Testing Library test foundation.
- ESLint, TypeScript and production-build gates.

## Deliberately excluded
Project/Site workflows, authentication UI, MapLibre, Planning Workspace, documents, GIS, AI and domain state are introduced in later controlled tasks.

## Local commands
```bash
npm install
npm run typecheck
npm run test
npm run lint
npm run build
npm run dev
```
