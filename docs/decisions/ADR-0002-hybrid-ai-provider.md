# ADR-0002 — Hybrid AI provider

## Decision
Implement a provider-neutral AI boundary with Ollama and OpenAI GPT-5.6 Luna.

## Rules
- Domain logic does not depend on provider-specific SDK objects.
- Provider output is advisory/orchestration output, never measurement authority.
- Provider health/failure must degrade safely.
- OpenAI credentials are optional at local boot; Ollama may serve as local provider when configured.
- Provider/model metadata is recorded on PlanningRun/synthesis outputs where relevant.
