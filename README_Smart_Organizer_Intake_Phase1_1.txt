GeoPilot Track B Smart Organizer Intake V1 - Phase 1.1

WHY THIS EXISTS
The Phase 1 installer correctly rolled back after its focused tests failed because
the project does not install pytest-asyncio. The feature code itself was not the
cause of that failure.

Phase 1.1 changes the focused test harness to use Python asyncio.run(), so no new
pytest plugin or dependency is installed.

HOW TO RUN
1. Extract this ZIP.
2. Copy ALL extracted files into the GeoPilot project root, overwriting the
   matching _smart_intake_* payload files when asked.
3. Run:
   .\install_geopilot_track_b_smart_organizer_intake_v1_phase1_1.bat

SAFETY
- no migration
- Smart Intake inspection does not write to DB
- old manual ingestion is preserved
- installer backs up modified files
- on failure it restores the source/test backup
- focused tests, existing Track B tests, frontend typecheck/build, and full
  backend regression must pass before installer reports PASS
