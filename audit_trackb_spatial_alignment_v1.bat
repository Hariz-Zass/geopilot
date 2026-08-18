@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo GeoPilot Track B Spatial Alignment Audit V1
echo READ-ONLY: site vs raster vs generated change geometry
echo ============================================================
echo.

docker compose config --services >nul 2>&1
if errorlevel 1 (
  echo BLOCKED: run from geopilot_v7 project root and ensure Docker is running.
  exit /b 1
)

@'
import json
import uuid
from pathlib import Path

from pyproj import Transformer
from shapely import wkt
from shapely.geometry import shape
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.raster import RasterDataset
from app.models.site import Site

PROJECT_ID = uuid.UUID("f7617e94-7d8c-47d0-8bed-635cf2f48579")

def site_geom(obj):
    raw = str(obj.geometry)
    if raw.upper().startswith("SRID="):
        raw = raw.split(";", 1)[1]
    return wkt.loads(raw)

def raster_wgs84_bbox(r):
    b = r.bounds or {}
    left, bottom, right, top = map(float, (b["left"], b["bottom"], b["right"], b["top"]))
    t = Transformer.from_crs(r.crs, "EPSG:4326", always_xy=True)
    pts = [t.transform(x, y) for x, y in ((left,bottom),(left,top),(right,bottom),(right,top))]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

def bbox_delta(a, b):
    return max(abs(a[i] - b[i]) for i in range(4))

s = get_session_factory()()
try:
    sites = {x.id: x for x in s.scalars(select(Site).where(Site.project_id == PROJECT_ID))}
    rasters = list(s.scalars(
        select(RasterDataset).where(
            RasterDataset.project_id == PROJECT_ID,
            RasterDataset.is_archived.is_(False),
        )
    ))

    print("PROJECT:", PROJECT_ID)
    print()

    for location in ("urban", "rural"):
        scoped = [r for r in rasters if (r.provenance or {}).get("location_type") == location]
        before = next((r for r in scoped if (r.provenance or {}).get("temporal_role") == "before"), None)
        after = next((r for r in scoped if (r.provenance or {}).get("temporal_role") == "after"), None)
        if not before or not after:
            print(location.upper(), "PAIR: MISSING")
            continue

        site = sites.get(before.site_id)
        sg = site_geom(site)
        sb = tuple(map(float, sg.bounds))
        rb1 = raster_wgs84_bbox(before)
        rb2 = raster_wgs84_bbox(after)

        print("=" * 78)
        print(location.upper())
        print("SITE:", site.name, site.id)
        print("SITE WGS84 BBOX:    ", tuple(round(x, 9) for x in sb))
        print("T1 RASTER:", before.name, before.crs)
        print("T1 WGS84 BBOX:      ", tuple(round(x, 9) for x in rb1))
        print("T2 WGS84 BBOX:      ", tuple(round(x, 9) for x in rb2))
        print("SITE vs T1 max deg: ", f"{bbox_delta(sb, rb1):.10f}")
        print("T1 vs T2 max deg:   ", f"{bbox_delta(rb1, rb2):.10f}")

        tol = 0.00010
        print("SITE-RASTER ALIGN:  ", "PASS" if bbox_delta(sb, rb1) <= tol else "FAIL")
        print("T1-T2 ALIGN:        ", "PASS" if bbox_delta(rb1, rb2) <= tol else "FAIL")
        print("SITE CENTROID:       ", round(sg.centroid.x, 9), round(sg.centroid.y, 9))

    print()
    print("=" * 78)
    print("LATEST CHANGE GEOJSON CHECK")
    root = Path("/data/rasters/analysis") / str(PROJECT_ID)
    geojsons = sorted(
        root.rglob("change_regions.geojson"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    if not geojsons:
        print("No change_regions.geojson found.")
    else:
        for p in geojsons[:4]:
            data = json.loads(p.read_text(encoding="utf-8"))
            geoms = [shape(f["geometry"]) for f in data.get("features", []) if f.get("geometry")]
            if not geoms:
                print(p, "NO FEATURES")
                continue
            minx = min(g.bounds[0] for g in geoms)
            miny = min(g.bounds[1] for g in geoms)
            maxx = max(g.bounds[2] for g in geoms)
            maxy = max(g.bounds[3] for g in geoms)
            print(p)
            print("  FEATURES:", len(geoms))
            print("  GEOJSON BBOX:", tuple(round(x, 9) for x in (minx,miny,maxx,maxy)))
finally:
    s.close()
'@ | docker compose exec -T backend python -

if errorlevel 1 (
  echo.
  echo SPATIAL ALIGNMENT AUDIT FAILED
  exit /b 1
)

echo.
echo ============================================================
echo AUDIT COMPLETE - no files or database records were modified.
echo ============================================================
