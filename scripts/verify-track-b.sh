#!/usr/bin/env sh
set -eu

echo "== GeoPilot Track B capability gate =="
python - <<'PY'
import rasterio
from app.core.config import get_settings
from app.services.track_b import _normalize_band_name
s=get_settings()
with rasterio.Env() as env:
    drivers=env.drivers()
assert drivers.get('GTiff'), 'GeoTIFF driver unavailable'
assert drivers.get('JP2OpenJPEG'), 'JP2OpenJPEG driver unavailable'
assert s.track_b_competition_mode is True, 'Track B closed-evidence mode must be enabled'
assert _normalize_band_name('red') == 'B04'
assert _normalize_band_name('nir') == 'B08'
print('GeoTIFF:', drivers.get('GTiff'))
print('JP2:', drivers.get('JP2OpenJPEG'))
print('Competition mode:', s.track_b_competition_mode)
print('Max analysis pixels:', s.track_b_max_analysis_pixels)
print('PASS — Track B runtime capability gate')
PY
