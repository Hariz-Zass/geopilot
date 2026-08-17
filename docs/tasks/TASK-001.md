# TASK-001 — Repository & Architecture Baseline

## Objective
Create the clean-room GeoPilot AI repository baseline and lock the authoritative rebuild architecture before feature implementation.

## Owner decisions
- Build and validate in the ChatGPT/local workflow, then provide runnable artifacts for the owner's Windows machine.
- Hybrid AI providers: Ollama + OpenAI GPT-5.6 Luna.
- Internet access is allowed.
- Sentinel-2 is the primary satellite source.
- Planning documents support user upload plus controlled acquisition/import.
- 100% clean rebuild; no old database/code/evidence/migrations.
- Do not Git commit until the project is complete and the owner explicitly authorizes it.

## In scope
- Repository layout.
- Architecture hard rules.
- Technology/runtime contract.
- Environment-variable contract.
- Architectural decision records.
- New task-state governance.
- Clean migration numbering policy.

## Out of scope
- FastAPI implementation.
- React implementation.
- Database schema/migration implementation.
- Docker services.
- Authentication.
- GIS/document/AI/satellite feature code.

## Acceptance criteria
- [x] Repository directory baseline exists.
- [x] Authoritative architecture is recorded.
- [x] Clean-room rule is explicit.
- [x] Hybrid provider choice is recorded.
- [x] Sentinel-2 primary provider choice is recorded.
- [x] Controlled document acquisition boundary is recorded.
- [x] Security/evidence hard rules are explicit.
- [x] Environment contract contains no secrets.
- [x] Migration sequence is defined to begin at 0001.
- [x] No application feature code has been introduced.
- [x] No Git commit has been created.

## Result
PASS — TASK-001 ARCHITECTURE BASELINE READY FOR TASK-002.
