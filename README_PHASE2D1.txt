GeoPilot Smart Organizer Phase 2D.1

Purpose:
Wire the accepted Smart Organizer backend into a controlled frontend workflow.

Flow:
1. Select organizer ZIP/multiple files.
2. Analyze package + discover Site candidates.
3. Choose a candidate or upload organizer GeoJSON boundary.
4. Confirm Site and build spatial import plan.
5. Explicitly assign a role to every IMPORT_CANDIDATE.
6. Run dry-run final review.
7. Tick final authorization checkbox.
8. CONFIRM & IMPORT ALL.

Safety:
- Existing Phase 1 inspect UI remains.
- Existing manual Track B ingestion remains.
- No backend production source modification.
- No migration.
- Installer does not execute Import All or write DB.
- Persistent write stays explicit and backend-controlled.

Run:
  .\install_geopilot_smart_organizer_phase2d1.bat

Result:
  artifacts\smart_organizer_phase2d1_result.txt
