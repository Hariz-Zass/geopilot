GeoPilot Smart Organizer FINAL Judge-Ready Closeout

This is a non-modifying closeout gate.

It performs:
- backend Smart Organizer route/service contract verification
- frontend controlled-import contract verification
- focused Smart Organizer regression
- full backend regression
- frontend typecheck
- frontend tests
- frontend production build
- runtime health checks
- final DB preservation audit

Expected DB baseline:
  alembic_revision = 0020
  sites = 2
  gis_layers = 0
  gis_features = 0
  acceptance fixtures = 0

No source modification.
No migration.
No DB write.

Run:
  .\run_geopilot_smart_organizer_FINAL_closeout.bat

Result:
  artifacts\smart_organizer_FINAL_judge_ready_closeout.txt
