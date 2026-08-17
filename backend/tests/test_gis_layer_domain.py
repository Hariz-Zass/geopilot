from __future__ import annotations
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import get_db_session
from app.db.base import Base
from app.main import create_app

@pytest.fixture()
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine=create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine); factory=sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
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
def project(c,t,name='P'):
    return c.post('/api/v1/projects',headers=h(t),json={'name':name}).json()['id']
def payload():
    return {'name':'  Parks  Layer ','description':' source polygons ','source_kind':'upload','source_name':'parks.geojson','source_checksum_sha256':'a'*64,'source_crs':'epsg:4326','geometry_type':'Polygon','provenance':{'authority':'owner_upload'}}

def test_requires_auth(client):
    assert client.get('/api/v1/projects/00000000-0000-0000-0000-000000000001/gis-layers').status_code==401

def test_create_normalizes_and_preserves_provenance(client):
    t=login(client,'a@example.com'); p=project(client,t)
    r=client.post(f'/api/v1/projects/{p}/gis-layers',headers=h(t),json=payload())
    assert r.status_code==201; b=r.json(); assert b['name']=='Parks Layer'; assert b['description']=='source polygons'; assert b['source_crs']=='EPSG:4326'; assert b['provenance']['authority']=='owner_upload'; assert b['project_id']==p

def test_upload_requires_source_name(client):
    t=login(client,'a@example.com'); p=project(client,t); x=payload(); x['source_name']=None
    r=client.post(f'/api/v1/projects/{p}/gis-layers',headers=h(t),json=x)
    assert r.status_code==422

def test_acquired_requires_uri(client):
    t=login(client,'a@example.com'); p=project(client,t); x=payload(); x.update(source_kind='acquired',source_name=None,source_uri=None)
    assert client.post(f'/api/v1/projects/{p}/gis-layers',headers=h(t),json=x).status_code==422

def test_cross_owner_and_cross_project_layer_substitution_fail_closed(client):
    a=login(client,'a@example.com'); b=login(client,'b@example.com'); pa=project(client,a,'A'); pa2=project(client,a,'A2')
    lid=client.post(f'/api/v1/projects/{pa}/gis-layers',headers=h(a),json=payload()).json()['id']
    assert client.get(f'/api/v1/projects/{pa}/gis-layers/{lid}',headers=h(b)).status_code==404
    r=client.get(f'/api/v1/projects/{pa2}/gis-layers/{lid}',headers=h(a)); assert r.status_code==404; assert r.json()['error']['code']=='gis_layer_not_found'

def test_archiving_deactivates_and_default_list_hides(client):
    t=login(client,'a@example.com'); p=project(client,t); lid=client.post(f'/api/v1/projects/{p}/gis-layers',headers=h(t),json=payload()).json()['id']
    r=client.patch(f'/api/v1/projects/{p}/gis-layers/{lid}',headers=h(t),json={'is_archived':True}); assert r.status_code==200; assert r.json()['is_active'] is False
    assert client.get(f'/api/v1/projects/{p}/gis-layers',headers=h(t)).json()==[]
    assert len(client.get(f'/api/v1/projects/{p}/gis-layers?include_archived=true',headers=h(t)).json())==1

def test_archived_project_rejects_new_layer(client):
    t=login(client,'a@example.com'); p=project(client,t); client.patch(f'/api/v1/projects/{p}',headers=h(t),json={'is_archived':True})
    r=client.post(f'/api/v1/projects/{p}/gis-layers',headers=h(t),json=payload()); assert r.status_code==409; assert r.json()['error']['code']=='gis_layer_state_invalid'

def test_delete_is_project_scoped(client):
    t=login(client,'a@example.com'); p=project(client,t); lid=client.post(f'/api/v1/projects/{p}/gis-layers',headers=h(t),json=payload()).json()['id']
    assert client.delete(f'/api/v1/projects/{p}/gis-layers/{lid}',headers=h(t)).status_code==204
    assert client.get(f'/api/v1/projects/{p}/gis-layers/{lid}',headers=h(t)).status_code==404
