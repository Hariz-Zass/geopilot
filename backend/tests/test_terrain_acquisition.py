from __future__ import annotations

import uuid
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

from app.db.base import Base
from app.models.project import Project
from app.models.site import Site
from app.models.user import User

@pytest.fixture()
def terrain_context():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def spatial_passthrough(dbapi_connection, connection_record):
        dbapi_connection.create_function("ST_GeomFromEWKT", 1, lambda value: value)
        dbapi_connection.create_function("ST_AsEWKT", 1, lambda value: value)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    with factory() as session:
        owner = User(email="terrain-owner@example.com", display_name="Terrain Owner", password_hash="test-only-password-hash", is_active=True)
        session.add(owner); session.flush()
        project = Project(owner_id=owner.id, name="Terrain Project", description="test")
        session.add(project); session.flush()
        site = Site(project_id=project.id, name="Terrain Site", geometry="SRID=4326;MULTIPOLYGON(((101.70 3.00,101.71 3.00,101.71 3.01,101.70 3.01,101.70 3.00)))", geometry_hash="0"*64, geometry_revision=1, is_active=True, is_archived=False)
        session.add(site); session.commit(); session.refresh(owner); session.refresh(project); session.refresh(site)
        yield session, owner, project, site
    Base.metadata.drop_all(engine); engine.dispose()


from app.models.raster import RasterDataset
from app.services.terrain_acquisition import (
    AcquiredTerrainArtifact,
    acquire_site_dem_if_missing,
    preferred_site_dem,
)


class FakeProvider:
    name = "fake_authoritative"

    def __init__(self, data: bytes):
        self.data = data

    def acquire(self, *, site_geometry: dict, target_crs: str):
        return AcquiredTerrainArtifact(
            data=self.data,
            provider="fake_authoritative",
            collection="fake-dem-test",
            scene_id="fake-scene-001",
            acquisition_datetime=None,
            source_reference="test://fake-dem",
            original_crs=target_crs,
            metadata={"test": True},
        )


def test_manual_dem_precedence(terrain_context):
    session, owner, project, site = terrain_context
    manual = RasterDataset(
        project_id=project.id,
        site_id=site.id,
        created_by_user_id=owner.id,
        name="Manual DEM",
        source_kind="upload",
        provider="user_supplied",
        collection="terrain-dem-v1",
        scene_id="manual",
        acquisition_datetime=None,
        crs="EPSG:32647",
        width=2,
        height=2,
        band_count=1,
        band_names=["ELEVATION"],
        pixel_size={"x": 10.0, "y": 10.0},
        bounds={"left": 0, "bottom": 0, "right": 20, "top": 20},
        nodata={"values": [None]},
        source_uri="local://rasters/manual.tif",
        checksum_sha256="a" * 64,
        provenance={
            "data_role": "dem",
            "terrain_type": "elevation",
            "evidence_scope": "project_site_user_supplied",
            "ingestion_method": "terrain_dem_upload_v1",
        },
        status="ready",
        is_archived=False,
    )
    auto = RasterDataset(
        project_id=project.id,
        site_id=site.id,
        created_by_user_id=owner.id,
        name="Auto DEM",
        source_kind="satellite_acquired",
        provider="copernicus_cdse",
        collection="copernicus-dem",
        scene_id="auto",
        acquisition_datetime=None,
        crs="EPSG:32647",
        width=2,
        height=2,
        band_count=1,
        band_names=["ELEVATION"],
        pixel_size={"x": 30.0, "y": 30.0},
        bounds={"left": 0, "bottom": 0, "right": 60, "top": 60},
        nodata={"values": [None]},
        source_uri="local://rasters/auto.tif",
        checksum_sha256="b" * 64,
        provenance={
            "data_role": "dem",
            "terrain_type": "elevation",
            "evidence_scope": "project_site_authoritative_acquired",
            "ingestion_method": "terrain_dem_auto_acquisition_v1",
        },
        status="ready",
        is_archived=False,
    )
    session.add_all([manual, auto])
    session.commit()
    selected = preferred_site_dem(session, project_id=project.id, site_id=site.id)
    assert selected.id == manual.id


def test_cdse_provider_uses_official_oauth_and_process_contract(monkeypatch):
    import json
    import httpx

    from app.core.config import get_settings
    from app.services.terrain_acquisition import CopernicusDemProvider

    get_settings.cache_clear()
    monkeypatch.setenv("TERRAIN_CDSE_CLIENT_ID", "test-client")
    monkeypatch.setenv("TERRAIN_CDSE_CLIENT_SECRET", "test-secret")
    get_settings.cache_clear()

    dem_bytes = _fake_dem_bytes()
    seen = {"token": None, "process": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/protocol/openid-connect/token"):
            body = request.content.decode("utf-8")
            seen["token"] = body
            assert "grant_type=client_credentials" in body
            assert "client_id=test-client" in body
            assert "client_secret=test-secret" in body
            return httpx.Response(200, json={"access_token": "unit-test-token", "expires_in": 300})

        if request.url.path == "/process/v1":
            assert request.headers.get("authorization") == "Bearer unit-test-token"
            payload = json.loads(request.content.decode("utf-8"))
            seen["process"] = payload
            assert payload["input"]["data"][0]["type"] == "dem"
            assert payload["input"]["data"][0]["dataFilter"]["demInstance"] == "COPERNICUS_30"
            assert payload["output"]["responses"][0]["format"]["type"] == "image/tiff"
            return httpx.Response(200, content=dem_bytes, headers={"content-type": "image/tiff"})

        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        artifact = CopernicusDemProvider(client=client).acquire(
            site_geometry={
                "type": "Polygon",
                "coordinates": [[[101.60, 3.00], [101.61, 3.00], [101.61, 3.01], [101.60, 3.01], [101.60, 3.00]]],
            },
            target_crs="EPSG:32647",
        )

    assert artifact.provider == "copernicus_cdse"
    assert artifact.collection == "copernicus-dem-glo-30"
    assert artifact.metadata["dem_instance"] == "COPERNICUS_30"
    assert seen["token"] is not None
    assert seen["process"] is not None
    get_settings.cache_clear()


def test_cdse_provider_rejects_failed_oauth(monkeypatch):
    import httpx
    import pytest

    from app.core.config import get_settings
    from app.services.terrain_acquisition import CopernicusDemProvider, TerrainAcquisitionError

    get_settings.cache_clear()
    monkeypatch.setenv("TERRAIN_CDSE_CLIENT_ID", "bad-client")
    monkeypatch.setenv("TERRAIN_CDSE_CLIENT_SECRET", "bad-secret")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TerrainAcquisitionError, match="HTTP 401"):
            CopernicusDemProvider(client=client).acquire(
                site_geometry={
                    "type": "Polygon",
                    "coordinates": [[[101.60, 3.00], [101.61, 3.00], [101.61, 3.01], [101.60, 3.01], [101.60, 3.00]]],
                },
                target_crs="EPSG:32647",
            )
    get_settings.cache_clear()


def _fake_dem_bytes() -> bytes:
    from rasterio.transform import from_origin

    profile = {
        "driver": "GTiff",
        "height": 4,
        "width": 4,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(101.60, 3.01, 0.0025, 0.0025),
    }
    with MemoryFile() as mem:
        with mem.open(**profile) as ds:
            ds.write(np.arange(16, dtype="float32").reshape(1, 4, 4))
        return mem.read()
