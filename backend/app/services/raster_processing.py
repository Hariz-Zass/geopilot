from __future__ import annotations
import numpy as np
class RasterProcessingError(Exception): pass

def ndvi(red, nir, *, nodata_mask=None):
    red=np.asarray(red,dtype='float64'); nir=np.asarray(nir,dtype='float64')
    if red.shape!=nir.shape: raise RasterProcessingError('Red and NIR arrays must have identical shape.')
    denom=nir+red
    out=np.full(red.shape,np.nan,dtype='float64')
    valid=np.isfinite(red)&np.isfinite(nir)&(denom!=0)
    if nodata_mask is not None: valid &= ~np.asarray(nodata_mask,dtype=bool)
    out[valid]=(nir[valid]-red[valid])/denom[valid]
    return out

def coverage_percent(mask):
    m=np.asarray(mask,dtype=bool)
    if m.size==0: return 0.0
    return float(np.count_nonzero(m)/m.size*100.0)
