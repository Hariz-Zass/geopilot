from __future__ import annotations
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import get_db_session
from app.db.base import Base
from app.main import create_app

@pytest.fixture()
def session_factory() -> Generator[sessionmaker[Session],None,None]:
    engine=create_engine('sqlite+pysqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=StaticPool)
    @event.listens_for(engine,'connect')
    def spatial(dbapi_connection, connection_record):
        dbapi_connection.create_function('ST_GeomFromEWKT',1,lambda v:v)
        dbapi_connection.create_function('ST_AsEWKT',1,lambda v:v)
    Base.metadata.create_all(engine); factory=sessionmaker(bind=engine,expire_on_commit=False,class_=Session)
    yield factory; Base.metadata.drop_all(engine); engine.dispose()

@pytest.fixture()
def client(session_factory):
    app=create_app()
    def override():
        with session_factory() as s: yield s
    app.dependency_overrides[get_db_session]=override
    with TestClient(app) as c: yield c

def login(c,email):
    pw='a-secure-password-123'; c.post('/api/v1/auth/register',json={'email':email,'display_name':'u','password':pw})
    return c.post('/api/v1/auth/login',json={'email':email,'password':pw}).json()['access_token']
def h(t): return {'Authorization':f'Bearer {t}'}
def project(c,t,name='P'): return c.post('/api/v1/projects',headers=h(t),json={'name':name}).json()['id']
def layer(c,t,p,geometry_type='Unknown'):
    payload={'name':'Evidence','source_kind':'upload','source_name':'evidence.geojson','source_crs':'EPSG:4326','geometry_type':geometry_type,'provenance':{'owner_upload':True}}
    return c.post(f'/api/v1/projects/{p}/gis-layers',headers=h(t),json=payload).json()['id']
def point(x=101.1,y=3.2): return {'type':'Point','coordinates':[x,y]}
def feature(fid='A',geom=None,props=None): return {'type':'Feature','id':fid,'geometry':geom or point(),'properties':props or {'name':'Alpha'}}

def test_feature_routes_require_auth(client):
    base='/api/v1/projects/00000000-0000-0000-0000-000000000001/gis-layers/00000000-0000-0000-0000-000000000002/features'
    assert client.get(base).status_code==401

def test_single_feature_create_persists_identity_and_properties(client):
    t=login(client,'a@example.com'); p=project(client,t); l=layer(client,t,p)
    r=client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t),json={'source_feature_id':' parcel-7 ','geometry':point(),'properties':{'zone':'R1','score':4}})
    assert r.status_code==201; b=r.json(); assert b['project_id']==p and b['layer_id']==l
    assert b['source_feature_id']=='parcel-7'; assert b['geometry']==point(); assert b['geometry_type']=='Point'
    assert len(b['geometry_hash'])==64 and b['properties']['zone']=='R1'

def test_feature_collection_ingest_is_atomic_and_preserves_source_ids(client):
    t=login(client,'a@example.com'); p=project(client,t); l=layer(client,t,p)
    payload={'type':'FeatureCollection','features':[feature(10,point(101,3)),feature('B',point(102,4),{'kind':'tree'})]}
    r=client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features/ingest',headers=h(t),json=payload)
    assert r.status_code==201; b=r.json(); assert b['count']==2; assert [x['source_feature_id'] for x in b['features']]==['10','B']
    assert len(client.get(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t)).json())==2

def test_batch_type_failure_rolls_back_entire_collection(client):
    t=login(client,'a@example.com'); p=project(client,t); l=layer(client,t,p)
    payload={'type':'FeatureCollection','features':[feature('P',point()),feature('L',{'type':'LineString','coordinates':[[101,3],[102,4]]})]}
    r=client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features/ingest',headers=h(t),json=payload)
    assert r.status_code==409
    assert client.get(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t)).json()==[]
    assert client.get(f'/api/v1/projects/{p}/gis-layers/{l}',headers=h(t)).json()['geometry_type']=='Unknown'

def test_declared_layer_geometry_type_is_enforced(client):
    t=login(client,'a@example.com'); p=project(client,t); l=layer(client,t,p,'Polygon')
    r=client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t),json={'geometry':point(),'properties':{}})
    assert r.status_code==409; assert r.json()['error']['code']=='gis_feature_state_invalid'

def test_unknown_layer_type_becomes_first_ingested_type(client):
    t=login(client,'a@example.com'); p=project(client,t); l=layer(client,t,p)
    client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t),json={'geometry':point(),'properties':{}})
    b=client.get(f'/api/v1/projects/{p}/gis-layers/{l}',headers=h(t)).json(); assert b['geometry_type']=='Point'

def test_inactive_or_archived_layer_rejects_ingestion(client):
    t=login(client,'a@example.com'); p=project(client,t); l=layer(client,t,p)
    client.patch(f'/api/v1/projects/{p}/gis-layers/{l}',headers=h(t),json={'is_active':False})
    assert client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t),json={'geometry':point(),'properties':{}}).status_code==409
    client.patch(f'/api/v1/projects/{p}/gis-layers/{l}',headers=h(t),json={'is_archived':True})
    assert client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t),json={'geometry':point(),'properties':{}}).status_code==409

def test_cross_owner_cross_project_and_cross_layer_feature_substitution_fail_closed(client):
    a=login(client,'a@example.com'); b=login(client,'b@example.com'); pa=project(client,a,'A'); pa2=project(client,a,'A2'); la=layer(client,a,pa); la2=layer(client,a,pa)
    fid=client.post(f'/api/v1/projects/{pa}/gis-layers/{la}/features',headers=h(a),json={'geometry':point(),'properties':{}}).json()['id']
    assert client.get(f'/api/v1/projects/{pa}/gis-layers/{la}/features/{fid}',headers=h(b)).status_code==404
    assert client.get(f'/api/v1/projects/{pa2}/gis-layers/{la}/features/{fid}',headers=h(a)).status_code==404
    r=client.get(f'/api/v1/projects/{pa}/gis-layers/{la2}/features/{fid}',headers=h(a)); assert r.status_code==404; assert r.json()['error']['code']=='gis_feature_not_found'

def test_archive_hides_feature_but_audit_list_can_include(client):
    t=login(client,'a@example.com'); p=project(client,t); l=layer(client,t,p)
    fid=client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t),json={'geometry':point(),'properties':{}}).json()['id']
    r=client.patch(f'/api/v1/projects/{p}/gis-layers/{l}/features/{fid}/archive',headers=h(t)); assert r.status_code==200 and r.json()['is_archived'] is True
    assert client.get(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t)).json()==[]
    assert len(client.get(f'/api/v1/projects/{p}/gis-layers/{l}/features?include_archived=true',headers=h(t)).json())==1

def test_invalid_coordinates_and_null_geometry_are_rejected(client):
    t=login(client,'a@example.com'); p=project(client,t); l=layer(client,t,p)
    r=client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t),json={'geometry':{'type':'Point','coordinates':[999,3]},'properties':{}}); assert r.status_code==422
    r=client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features/ingest',headers=h(t),json={'type':'FeatureCollection','features':[{'type':'Feature','geometry':None,'properties':{}}]}); assert r.status_code==422

def test_polygon_ring_validation(client):
    t=login(client,'a@example.com'); p=project(client,t); l=layer(client,t,p,'Polygon')
    bad={'type':'Polygon','coordinates':[[[101,3],[102,3],[102,4],[101.5,4]]]}
    assert client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t),json={'geometry':bad,'properties':{}}).status_code==422

def test_delete_removes_only_exact_feature(client):
    t=login(client,'a@example.com'); p=project(client,t); l=layer(client,t,p)
    fid=client.post(f'/api/v1/projects/{p}/gis-layers/{l}/features',headers=h(t),json={'geometry':point(),'properties':{}}).json()['id']
    assert client.delete(f'/api/v1/projects/{p}/gis-layers/{l}/features/{fid}',headers=h(t)).status_code==204
    assert client.get(f'/api/v1/projects/{p}/gis-layers/{l}/features/{fid}',headers=h(t)).status_code==404
