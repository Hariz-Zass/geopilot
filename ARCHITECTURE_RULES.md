# GeoPilot AI Architecture Rules

These rules are hard gates for the clean-room rebuild.

1. Evidence first: material claims must trace to a controlled source, persisted fact, deterministic result, GIS/raster source, or explicit user input.
2. The LLM is never authoritative for spatial measurements, policy numbers, geometry, satellite metadata, dates, compliance status, suitability scoring, or raster calculations.
3. Project and site isolation is mandatory. Cross-project evidence reuse fails closed unless an explicitly designed feature authorizes it.
4. Exact evidence lineage must be preserved whenever an evidence identity exists.
5. Missing, stale, conflicting, incomplete, malformed, duplicated, or ambiguous evidence must be surfaced rather than silently resolved.
6. Compliance, Suitability, GIS, raster/satellite, document retrieval, Planning Officer orchestration, and professional review remain distinct domains.
7. The Planning Officer is a bounded orchestrator. It may only invoke server-owned, typed, authorized tools.
8. The Planning Officer receives no arbitrary SQL, Python, shell, filesystem, provider-defined tool registration, or arbitrary URL execution capability.
9. Deterministic engines are authoritative for measurable outputs. AI may interpret and synthesize validated evidence only.
10. Frontend code must render server-produced authoritative values and must not recompute authoritative planning/spatial/raster measurements.
11. Finding geometry and map actions must resolve from server-owned validated geometry identities.
12. Synthetic fixtures are allowed only inside testing boundaries and must never be presented as official planning evidence.
13. Unresolved states are valid outcomes: insufficient_evidence, missing_evidence, configuration_invalid, requires_professional_review, provider_unavailable, incompatible_temporal_scenes, insufficient_raster_coverage, ambiguous_duplicate_evidence, malformed_or_archived_source, degraded_map_geometry, clarification_required.
14. GeoPilot AI must not produce autonomous statutory approval/rejection, legal conclusions, or statutory certification.
15. Human professional review remains authoritative for material planning interpretation and statutory decisions.
16. Implementation completion and real-data acceptance are separate gates.
17. New database migrations must be justified by a proven persistence requirement and must be task-scoped.
18. The rebuild starts with migration 0001; no legacy migration chain is imported.
19. Secrets must not be committed or stored in tracked configuration.
20. No Git commits, tags, or pushes are authorized until explicit owner approval after the project is complete.
