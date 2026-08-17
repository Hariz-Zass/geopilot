# GeoPilot AI — Final Local Deployment & Acceptance Runbook

This runbook is intentionally deferred until the owner is ready to deploy the final snapshot on the Windows laptop.

## Required local components
- Docker Desktop with Compose
- Git (optional; repository currently intentionally has no commits)
- Ollama for the local Planning/Embedding provider path
- Internet access for OpenAI and Copernicus/Sentinel provider paths
- A configured OpenAI API key if OpenAI fallback is enabled

## Controlled sequence
1. Extract only the latest final GeoPilot snapshot into the working directory.
2. Copy `.env.example` to `.env` and replace all secrets/placeholders.
3. Confirm Docker Desktop is healthy.
4. Start database/backend/frontend with Docker Compose.
5. Confirm backend liveness and database readiness.
6. Run `alembic upgrade head`; expected head is `0020`.
7. Confirm PostgreSQL, PostGIS, and pgvector readiness.
8. Run the complete backend pytest suite.
9. Install frontend dependencies and run typecheck, tests, lint, and production build.
10. Perform browser acceptance: register/login, project, site, map, GIS layer/feature, planning document ingestion/chunk/index/retrieval/citation, policy workflow, Compliance, Suitability, raster/satellite, PlanningRun, report and professional review.
11. Configure Ollama models and verify local AI provider.
12. Configure OpenAI and verify failover provider.
13. Verify Copernicus Sentinel-2 catalogue access and legitimate scene provenance.
14. Run a legitimate real-data Suitability acceptance case; do not invent a threshold.
15. Run a legitimate real-imagery temporal NDVI case with >=90% usable target coverage and professional review.
16. Complete final competition/golden-path walkthrough.

Implementation completion is not the same as legitimate real-data acceptance. Missing evidence is a valid unresolved state.
