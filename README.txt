GeoPilot Phase 2C.3B Controlled Commit Acceptance

This is NOT another installer. It validates the installed Phase 2C.3B persistent
Import All path with a tiny synthetic organizer GeoPackage.

Flow:
1. Build a 3-feature GeoPackage fixture.
2. Use a temporary confirmed Site boundary.
3. Execute a REAL persistent Import All.
4. Verify only the two intersecting polygons persist.
5. Verify planning applicability role provenance.
6. Re-run to verify Site/layer reuse and feature duplicate protection.
7. Delete committed fixture Site/layer/features.
8. Restore original Site active states.
9. Confirm database counts return to baseline.

The sample organizer ZIP used earlier is NOT persisted.

Run:
  .\run_phase2c3b_controlled_commit_acceptance.bat

Result:
  artifacts\smart_organizer_phase2c3b_controlled_commit_acceptance.txt
