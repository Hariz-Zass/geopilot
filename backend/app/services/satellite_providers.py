from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import httpx
class SatelliteProviderError(Exception): pass
@dataclass(frozen=True)
class SatelliteScene:
    provider:str; collection:str; scene_id:str; acquisition_datetime:str; assets:dict[str,Any]; geometry:dict|None; bbox:list|None; cloud_cover:float|None
class CopernicusSentinel2Provider:
    name='copernicus_cdse'; collection='sentinel-2-l2a'; base_url='https://stac.dataspace.copernicus.eu/v1'
    def search(self, *, bbox:list[float], datetime_range:str, limit:int=20)->list[SatelliteScene]:
        payload={'collections':[self.collection],'bbox':bbox,'datetime':datetime_range,'limit':min(max(limit,1),100)}
        try:
            r=httpx.post(f'{self.base_url}/search',json=payload,timeout=30); r.raise_for_status(); data=r.json()
        except Exception as exc: raise SatelliteProviderError('Copernicus STAC provider unavailable.') from exc
        out=[]
        for f in data.get('features',[]):
            p=f.get('properties',{}); out.append(SatelliteScene(self.name,self.collection,str(f.get('id')),str(p.get('datetime')),dict(f.get('assets',{})),f.get('geometry'),f.get('bbox'),p.get('eo:cloud_cover')))
        return out
