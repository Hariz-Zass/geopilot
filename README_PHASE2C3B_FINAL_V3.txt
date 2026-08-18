GeoPilot Phase 2C.3B Controlled Commit Acceptance FINAL V3

This repairs the V2 acceptance-wrapper blocker:

    TypeError: '<' not supported between instances of 'NoneType' and 'NoneType'

Root cause:
V2 sorted GISFeature.source_feature_id values after converting the synthetic
GeoJSON fixture through GeoPackage. The GeoPackage/GDAL conversion is not
required to preserve GeoJSON top-level Feature.id into the normalized output,
so persisted source_feature_id values may legitimately be None.

This is an ACCEPTANCE WRAPPER issue, not a persistent Import All engine issue.

V3 changes acceptance verification only:
- fixture adds a stable `fixture_key` property;
- verifies persisted A1/A2 using properties;
- verifies OUTSIDE was not persisted;
- verifies two distinct 64-char geometry_hash values;
- second-run duplicate protection is verified by stable feature count and
  features_duplicates_skipped == 2;
- does NOT modify production source;
- does NOT create a migration;
- runs real commit, second-run reuse, cleanup, independent DB audit, focused regression;
- writes stdout/stderr reliably to a single result log.

Copy all files to geopilot_v7 and run:

  .\run_phase2c3b_controlled_commit_acceptance_FINAL_V3.bat

Send back:
  artifacts\phase_2c3b_controlled_commit_acceptance_FINAL_V3.txt
