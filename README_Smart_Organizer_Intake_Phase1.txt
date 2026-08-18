GeoPilot Track B Smart Organizer Intake V1 - Phase 1

Copy ALL 4 files into the GeoPilot project root:
1. install_geopilot_track_b_smart_organizer_intake_v1_phase1.bat
2. install_geopilot_track_b_smart_organizer_intake_v1_phase1.ps1
3. _smart_intake_service_payload.py.txt
4. _smart_intake_test_payload.py.txt

Then run from PowerShell:
.\install_geopilot_track_b_smart_organizer_intake_v1_phase1.bat

Phase 1 is inspect-only:
- no migration
- Smart Intake inspection performs no DB writes
- existing manual Track B ingestion remains available
- focused + Track B + full backend regressions are run
- frontend typecheck/build are run
