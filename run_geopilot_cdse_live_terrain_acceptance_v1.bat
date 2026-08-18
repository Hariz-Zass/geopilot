@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo GeoPilot CDSE Live Terrain Acceptance V1
echo OAuth + Copernicus DEM GLO-30 + GeoTIFF validation
echo NO DB WRITE / NO MIGRATION / NO FRONTEND CHANGE
echo ============================================================
echo.

echo [1] Runtime safety/config gate
docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); ok=bool(s.terrain_cdse_client_id) and bool(s.terrain_cdse_client_secret) and s.terrain_auto_acquisition_enabled and s.terrain_auto_provider=='copernicus_cdse'; print('CLIENT_ID configured:', bool(s.terrain_cdse_client_id)); print('CLIENT_SECRET configured:', bool(s.terrain_cdse_client_secret)); print('AUTO_ACQUISITION_ENABLED:', s.terrain_auto_acquisition_enabled); print('PROVIDER:', s.terrain_auto_provider); raise SystemExit(0 if ok else 2)"
if errorlevel 1 (
  echo.
  echo BLOCKED: runtime configuration gate failed.
  pause
  exit /b 1
)

echo.
echo [2] Re-run local terrain regression before live network
docker compose exec -T backend python -m pytest -q tests/test_terrain_acquisition.py
if errorlevel 1 (
  echo.
  echo BLOCKED: local terrain regression failed.
  pause
  exit /b 1
)

echo.
echo [3] Live CDSE provider request on a very small Malaysia AOI
echo     This does NOT create a RasterDataset or write to PostgreSQL.
echo     Access token and credentials will NOT be printed.
echo.

docker compose exec -T backend python -c "from app.services.terrain_acquisition import CopernicusDemProvider,_normalize_dem_to_metric_geotiff,TerrainAcquisitionError; from rasterio.io import MemoryFile; import numpy as np; g={'type':'Polygon','coordinates':[[[101.7000,3.0000],[101.7020,3.0000],[101.7020,3.0020],[101.7000,3.0020],[101.7000,3.0000]]]}; print('LIVE_AOI:', '0.002 x 0.002 degrees'); a=CopernicusDemProvider().acquire(site_geometry=g,target_crs='EPSG:32647'); print('CDSE authentication + Process API: PASS'); print('Provider:',a.provider); print('Collection:',a.collection); print('Payload bytes:',len(a.data)); m=MemoryFile(a.data); ds=m.open(); arr=ds.read(1,masked=True); print('Source raster driver:',ds.driver); print('Source raster CRS:',ds.crs); print('Source raster size:',str(ds.width)+'x'+str(ds.height)); print('Usable elevation pixels:',int(arr.count())); print('Elevation min/max m:',float(arr.min()),float(arr.max())); ds.close(); m.close(); n,meta=_normalize_dem_to_metric_geotiff(a.data,target_crs='EPSG:32647'); print('Normalization: PASS'); print('Normalized CRS:',meta['crs']); print('Normalized size:',str(meta['width'])+'x'+str(meta['height'])); print('Normalized bytes:',len(n)); print('Provenance dataset:',a.metadata.get('dataset')); print('DEM instance:',a.metadata.get('dem_instance'))"
if errorlevel 1 (
  echo.
  echo ============================================================
  echo LIVE CDSE ACCEPTANCE FAILED
  echo ============================================================
  echo Do NOT alter credentials blindly.
  echo Paste the complete sanitized error output back into ChatGPT.
  echo No DB write was attempted by this acceptance script.
  echo ============================================================
  echo.
  pause
  exit /b 1
)

echo.
echo [4] Service health after external-provider test
docker compose ps
if errorlevel 1 (
  echo BLOCKED: docker compose status check failed.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo GEOPILOT CDSE LIVE TERRAIN ACCEPTANCE V1 PASS
echo ============================================================
echo OAuth client credentials: ACCEPTED
echo CDSE Sentinel Hub Process API: REACHABLE
echo Copernicus DEM GLO-30 response: VALID
echo GeoTIFF raster validation: PASS
echo Existing metric normalization: PASS
echo Manual DEM regression: PASS
echo Database write: NONE
echo Migration: NONE
echo Frontend change: NONE
echo Credential/token output: NONE
echo ============================================================
echo.
pause
exit /b 0
