# ADR-0003 — Sentinel-2 primary satellite source

## Decision
Sentinel-2 is the primary v1 satellite source behind a provider adapter boundary.

## Rules
- Acquisition/import must capture source identity, product/collection, acquisition time, bands, CRS/resolution, licensing/provenance, and validation state.
- Temporal analysis does not infer source truth from filenames or upload order.
- Future Landsat or other providers must plug into the same typed contract.
