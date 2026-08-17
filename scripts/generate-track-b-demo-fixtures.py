#!/usr/bin/env python3
"""Generate synthetic Track B raster fixtures for LOCAL QA ONLY.

These files are not organizer evidence and must never be used as hackathon evidence.
They exist only to validate GeoPilot ingestion, temporal measurement, maps, AI plumbing,
and reporting before the organizer releases the real challenge data.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "track_b_demo_fixtures"
OUT.mkdir(parents=True, exist_ok=True)


def write_scene(path: Path, *, urban: bool, after: bool) -> None:
    h = w = 128
    yy, xx = np.mgrid[0:h, 0:w]
    base_red = 0.20 + 0.03 * np.sin(xx / 10) + 0.02 * np.cos(yy / 13)
    base_nir = 0.55 + 0.04 * np.cos(xx / 15) - 0.02 * np.sin(yy / 12)
    if urban:
        # Urban QA: simulated vegetation loss / surface change in a compact eastern block.
        region = (xx > 70) & (xx < 112) & (yy > 30) & (yy < 92)
        if after:
            base_red[region] = 0.36
            base_nir[region] = 0.30
    else:
        # Rural QA: smaller fragmented change band.
        region = ((xx - 78) ** 2 + (yy - 70) ** 2 < 22 ** 2) | ((xx - 42) ** 2 + (yy - 42) ** 2 < 12 ** 2)
        if after:
            base_red[region] = 0.31
            base_nir[region] = 0.34

    data = np.stack([base_red, base_nir]).astype("float32")
    transform = from_origin(750000 if urban else 760000, 350000 if urban else 360000, 10, 10)
    with rasterio.open(
        path, "w", driver="GTiff", height=h, width=w, count=2, dtype="float32",
        crs="EPSG:32647", transform=transform, nodata=-9999.0, compress="deflate",
    ) as dst:
        dst.write(data)
        dst.set_band_description(1, "B04")
        dst.set_band_description(2, "B08")
        dst.update_tags(
            GEOPILOT_FIXTURE="synthetic_acceptance_only",
            EVIDENCE_WARNING="NOT_ORGANIZER_EVIDENCE",
        )


scenes = []
for location in ("urban", "rural"):
    for role, date in (("before", "20260115"), ("after", "20260715")):
        name = f"DEMO_ONLY_{location}_{role}_{date}_B04_B08.tif"
        path = OUT / name
        write_scene(path, urban=location == "urban", after=role == "after")
        scenes.append({"file": name, "location_type": location, "temporal_role": role, "data_stage": "raw", "band_names": ["B04", "B08"], "date": date})

manifest = {
    "warning": "SYNTHETIC QA FIXTURE ONLY. NOT ORGANIZER EVIDENCE. DO NOT USE IN COMPETITION SUBMISSION.",
    "purpose": "Local acceptance testing of GeoPilot Track B before real organizer datasets are released.",
    "recommended_mode": "ndvi",
    "scenes": scenes,
}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
(OUT / "DEMO_ONLY_NOT_COMPETITION_EVIDENCE.txt").write_text(manifest["warning"] + "\n", encoding="utf-8")
print(OUT)
for scene in scenes:
    print(scene["file"])
