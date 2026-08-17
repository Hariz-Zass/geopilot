import numpy as np,pytest
from types import SimpleNamespace
from app.schemas.temporal import TemporalThresholdPolicy
from app.services.temporal import compare_ndvi_arrays,validate_temporal_sources,TemporalError
from app.services.provider_resilience import golden_path_contract

def test_temporal_90_percent_boundary():
 mask=np.ones((10,10),dtype=bool); mask[0,:]=False
 r=compare_ndvi_arrays(red_before=np.ones((10,10)),nir_before=np.ones((10,10))*2,red_after=np.ones((10,10)),nir_after=np.ones((10,10))*3,coverage_mask=mask,threshold_policy=TemporalThresholdPolicy(absolute_delta_threshold=.1)); assert r['usable_coverage_percent']==90.0

def test_temporal_below_90_rejected():
 mask=np.zeros((10,10),dtype=bool); mask[:8,:]=True
 with pytest.raises(TemporalError): compare_ndvi_arrays(red_before=np.ones((10,10)),nir_before=np.ones((10,10))*2,red_after=np.ones((10,10)),nir_after=np.ones((10,10))*3,coverage_mask=mask,threshold_policy=TemporalThresholdPolicy())
def test_temporal_requires_same_provider_product_ordered_dates_and_bands():
 a=SimpleNamespace(provider='copernicus_cdse',collection='sentinel-2-l2a',acquisition_datetime='2026-01-01T00:00:00Z',crs='EPSG:32647',band_names=['B04','B08']); b=SimpleNamespace(provider='copernicus_cdse',collection='sentinel-2-l2a',acquisition_datetime='2026-02-01T00:00:00Z',crs='EPSG:32647',band_names=['B04','B08']); validate_temporal_sources(a,b)
def test_golden_path_never_claims_statutory_engine(): assert golden_path_contract()['statutory_decision_engine'] is False
