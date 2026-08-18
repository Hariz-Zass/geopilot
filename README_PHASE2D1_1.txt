GeoPilot Smart Organizer Phase 2D.1.1

Repair for the failed Phase 2D.1 frontend typecheck.

Exact TypeScript repairs:
1. The recommended Site candidate expression previously produced
   "" | TrackBOrganizerSiteCandidate because it used logical_name && find(...).
   V1.1 narrows recommendedName explicitly and returns candidate | undefined.

2. With strict indexed access, roles[item.logical_name] is string | undefined.
   V1.1 stores it in existingRole and narrows it before assignment.

The previous failed installer restored the frontend backup. This installer also
refuses to continue if the Phase 2D.1 marker is unexpectedly still present.

No backend production change.
No migration.
No installer DB write.

Run:
  .\install_geopilot_smart_organizer_phase2d1_1.bat

Result:
  artifacts\smart_organizer_phase2d1_1_result.txt
