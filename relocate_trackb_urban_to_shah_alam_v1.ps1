
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================"
Write-Host "GeoPilot Track B Urban Mainland Relocation V1"
Write-Host "Controlled demo georeference relocation - Shah Alam mainland"
Write-Host "Preserves raster pixel values; changes geospatial reference only"
Write-Host "Rural datasets and Track B source code are not modified"
Write-Host "============================================================"
Write-Host ""

$PROJECT_ID = "f7617e94-7d8c-47d0-8bed-635cf2f48579"
$SITE_ID = "2ea1e98d-347c-4a0a-8e5b-5dd7f9553673"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = ".\artifacts\trackb_mainland_relocation_backup_$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null

Write-Host "[1/6] Pre-mutation database + raster backup..."
docker compose exec -T backend python -c @"
import uuid, json, shutil
from pathlib import Path
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.site import Site
from app.models.raster import RasterDataset

project_id=uuid.UUID('$PROJECT_ID')
site_id=uuid.UUID('$SITE_ID')
out=Path('/workspace/artifacts/trackb_mainland_relocation_backup_$stamp')
out.mkdir(parents=True,exist_ok=True)
root=Path(get_settings().raster_storage_root).resolve()
s=get_session_factory()()
try:
    site=s.scalar(select(Site).where(Site.id==site_id,Site.project_id==project_id))
    rows=list(s.scalars(select(RasterDataset).where(RasterDataset.project_id==project_id,RasterDataset.site_id==site_id,RasterDataset.is_archived.is_(False))))
    payload={'site':{
        'id':str(site.id),'name':site.name,'geometry':str(site.geometry),
        'geometry_hash':site.geometry_hash,'geometry_revision':site.geometry_revision,
        'is_active':site.is_active,'is_archived':site.is_archived
    },'rasters':[]}
    for x in rows:
        d={'id':str(x.id),'name':x.name,'crs':x.crs,'width':x.width,'height':x.height,
           'band_count':x.band_count,'band_names':x.band_names,'pixel_size':x.pixel_size,
           'bounds':x.bounds,'source_uri':x.source_uri,'checksum_sha256':x.checksum_sha256,
           'provenance':x.provenance}
        payload['rasters'].append(d)
        if x.source_uri and x.source_uri.startswith('local://rasters/'):
            p=(root/x.source_uri[len('local://rasters/'):]).resolve()
            shutil.copy2(p,out/(str(x.id)+p.suffix))
    (out/'baseline.json').write_text(json.dumps(payload,indent=2,default=str),encoding='utf-8')
    print('BACKUP:',out)
    print('URBAN RASTER COUNT:',len(rows))
finally:
    s.close()
"@
if ($LASTEXITCODE -ne 0) { throw "Backup gate failed" }

Write-Host ""
Write-Host "[2/6] Relocating Urban demo georeference to Shah Alam mainland..."
docker compose exec -T backend python -c @"
import uuid, hashlib, os, json
from types import SimpleNamespace
from pathlib import Path
import rasterio
from rasterio.transform import from_origin
from pyproj import Transformer
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.site import Site
from app.models.raster import RasterDataset
from app.schemas.site import canonical_multipolygon, geometry_digest, multipolygon_to_ewkt

project_id=uuid.UUID('$PROJECT_ID')
site_id=uuid.UUID('$SITE_ID')
target_lon=101.52187
target_lat=3.07234
width=128
height=128
res=10.0

to_utm=Transformer.from_crs('EPSG:4326','EPSG:32647',always_xy=True)
to_wgs=Transformer.from_crs('EPSG:32647','EPSG:4326',always_xy=True)
cx,cy=to_utm.transform(target_lon,target_lat)
left=round((cx-(width*res/2.0))/10.0)*10.0
top=round((cy+(height*res/2.0))/10.0)*10.0
right=left+width*res
bottom=top-height*res
transform=from_origin(left,top,res,res)

minlon,minlat=to_wgs.transform(left,bottom)
maxlon,maxlat=to_wgs.transform(right,top)
geometry=SimpleNamespace(type='Polygon',coordinates=[[[minlon,minlat],[maxlon,minlat],[maxlon,maxlat],[minlon,maxlat],[minlon,minlat]]])
coords=canonical_multipolygon(geometry)
digest=geometry_digest(coords)

root=Path(get_settings().raster_storage_root).resolve()
s=get_session_factory()()
try:
    site=s.scalar(select(Site).where(Site.id==site_id,Site.project_id==project_id))
    if site is None:
        raise RuntimeError('Urban Site not found')
    rows=list(s.scalars(select(RasterDataset).where(
        RasterDataset.project_id==project_id,
        RasterDataset.site_id==site_id,
        RasterDataset.is_archived.is_(False)
    )))
    if len(rows)!=2:
        raise RuntimeError(f'Expected exactly 2 active Urban rasters; found {len(rows)}')
    for x in rows:
        if x.crs!='EPSG:32647' or x.width!=128 or x.height!=128:
            raise RuntimeError(f'Unexpected Urban raster grid for {x.id}')
        if (x.provenance or {}).get('location_type')!='urban':
            raise RuntimeError(f'Non-urban dataset unexpectedly linked to target Site: {x.id}')

    replacements=[]
    for x in rows:
        uri=x.source_uri or ''
        if not uri.startswith('local://rasters/'):
            raise RuntimeError(f'Urban raster is not a local immutable artifact: {x.id}')
        src=(root/uri[len('local://rasters/'):]).resolve()
        if not src.is_file():
            raise RuntimeError(f'Missing source raster: {src}')
        with rasterio.open(src) as ds:
            data=ds.read()
            profile=ds.profile.copy()
            if ds.crs is None or ds.crs.to_string()!='EPSG:32647':
                raise RuntimeError(f'Unexpected file CRS for {x.id}: {ds.crs}')
            profile.update(transform=transform,crs='EPSG:32647')
        tmp=src.parent/(f'.relocate_{x.id}.tif')
        with rasterio.open(tmp,'w',**profile) as dst:
            dst.write(data)
            for i,desc in enumerate(x.band_names or [],1):
                if i<=dst.count:
                    dst.set_band_description(i,str(desc))
        payload=tmp.read_bytes()
        sha=hashlib.sha256(payload).hexdigest()
        dst=src.parent/(sha+'.tif')
        if dst.exists():
            if hashlib.sha256(dst.read_bytes()).hexdigest()!=sha:
                raise RuntimeError('Checksum collision/mismatch')
            tmp.unlink()
        else:
            os.replace(tmp,dst)
        new_uri='local://rasters/'+dst.relative_to(root).as_posix()
        prov=dict(x.provenance or {})
        prov['transform']=[res,0.0,left,0.0,-res,top]
        prov['demo_georeference_relocated']=True
        prov['demo_georeference_location']='Shah Alam, Selangor, Malaysia'
        prov['demo_georeference_anchor_wgs84']={'longitude':target_lon,'latitude':target_lat}
        prov['demo_georeference_note']='Demo raster pixel values preserved; geospatial reference relocated to mainland Shah Alam for spatially credible visualization.'
        replacements.append((x,new_uri,sha,prov))

    site.geometry=multipolygon_to_ewkt(coords)
    site.geometry_hash=digest
    site.geometry_revision += 1
    if 'Urban Challenge Area' in site.name:
        site.name='Urban QA T1 - Shah Alam Urban Challenge Area'

    for x,new_uri,sha,prov in replacements:
        x.bounds={'left':left,'bottom':bottom,'right':right,'top':top}
        x.pixel_size={'x':res,'y':res}
        x.source_uri=new_uri
        x.checksum_sha256=sha
        x.provenance=prov

    s.commit()
    print('TARGET ANCHOR WGS84:',target_lon,target_lat)
    print('NEW UTM BOUNDS:',left,bottom,right,top)
    print('NEW WGS84 BBOX:',minlon,minlat,maxlon,maxlat)
    print('SITE GEOMETRY REVISION:',site.geometry_revision)
    for x,new_uri,sha,prov in replacements:
        print(x.name,x.id,sha,new_uri)
except:
    s.rollback()
    raise
finally:
    s.close()
"@
if ($LASTEXITCODE -ne 0) { throw "Relocation mutation failed; backup exists at $backup" }

Write-Host ""
Write-Host "[3/6] Spatial + checksum verification..."
docker compose exec -T backend python -c @"
import uuid, hashlib
from pathlib import Path
import rasterio
from pyproj import Transformer
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.site import Site
from app.models.raster import RasterDataset

project_id=uuid.UUID('$PROJECT_ID'); site_id=uuid.UUID('$SITE_ID')
root=Path(get_settings().raster_storage_root).resolve()
s=get_session_factory()()
try:
    site=s.scalar(select(Site).where(Site.id==site_id,Site.project_id==project_id))
    rows=list(s.scalars(select(RasterDataset).where(RasterDataset.project_id==project_id,RasterDataset.site_id==site_id,RasterDataset.is_archived.is_(False))))
    print('SITE:',site.name)
    print('GEOMETRY:',site.geometry)
    print('REVISION:',site.geometry_revision)
    bounds=[]
    for x in rows:
        p=(root/x.source_uri[len('local://rasters/'):]).resolve()
        sha=hashlib.sha256(p.read_bytes()).hexdigest()
        print(x.name,'DB_SHA_MATCH=',sha==x.checksum_sha256)
        with rasterio.open(p) as ds:
            b=(ds.bounds.left,ds.bounds.bottom,ds.bounds.right,ds.bounds.top)
            bounds.append(b)
            print(' ',x.id,'CRS=',ds.crs,'BOUNDS=',b,'TRANSFORM=',tuple(ds.transform)[:6])
    if len(set(bounds))!=1:
        raise RuntimeError('Urban T1/T2 bounds differ after relocation')
    print('T1-T2 ALIGN: PASS')
finally:
    s.close()
"@
if ($LASTEXITCODE -ne 0) { throw "Post-relocation spatial/checksum verification failed" }

Write-Host ""
Write-Host "[4/6] Track B regression baseline..."
docker compose exec -e PYTHONPATH=/app -T backend pytest -q tests/test_track_b_hackathon.py
if ($LASTEXITCODE -ne 0) { throw "Track B regression failed" }

Write-Host ""
Write-Host "[5/6] Readiness verification..."
docker compose exec -T backend python -c @"
import uuid
from sqlalchemy import select
from app.db.session import get_session_factory
from app.models.project import Project
from app.models.user import User
from app.services.track_b_acceptance import assess_track_b_readiness

pid=uuid.UUID('$PROJECT_ID')
s=get_session_factory()()
try:
    p=s.scalar(select(Project).where(Project.id==pid))
    if p is None: raise RuntimeError('Project not found')
    owner=s.scalar(select(User).where(User.id==p.owner_user_id))
    r=assess_track_b_readiness(s,owner=owner,project_id=pid)
    print('STATUS=',r['status'])
    print('URBAN=',r['urban'])
    print('RURAL=',r['rural'])
    print('BLOCKERS=',r['blockers'])
    if r['status']!='ready' or not r['urban']['ready'] or not r['rural']['ready']:
        raise RuntimeError('Track B readiness is not fully ready')
finally:
    s.close()
"@
if ($LASTEXITCODE -ne 0) { throw "Readiness gate failed" }

Write-Host ""
Write-Host "[6/6] Container status..."
docker compose ps

Write-Host ""
Write-Host "============================================================"
Write-Host "URBAN MAINLAND RELOCATION V1 GATE PASS"
Write-Host "Urban QA georeference is now anchored in mainland Shah Alam."
Write-Host "Raster pixel values were preserved; geospatial reference changed."
Write-Host "Rural QA and Track B source code were not modified."
Write-Host "Refresh GeoPilot with Ctrl+F5 and inspect the Urban map."
Write-Host "Do NOT run another Full Track B Mission yet."
Write-Host "============================================================"
