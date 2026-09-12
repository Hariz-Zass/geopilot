import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.artifact_storage import (
    ArtifactStorageError,
    LocalArtifactStorage,
    VercelBlobArtifactStorage,
    immutable_key,
)
from app.services.artifact_migration import migrate_raster_dataset
from app.models.raster import RasterDataset


def test_local_round_trip_is_immutable_and_checksum_verified(tmp_path: Path):
    storage = LocalArtifactStorage(tmp_path)
    data = b"real-raster-bytes"
    checksum = hashlib.sha256(data).hexdigest()
    key = immutable_key(uuid.uuid4(), "organizer", checksum, ".tif")
    uri = storage.put(key, data, checksum)
    assert uri.startswith("local://rasters/")
    assert storage.exists(uri)
    assert storage.read(uri, checksum) == data
    assert storage.put(key, data, checksum) == uri


def test_existing_object_with_wrong_content_is_rejected(tmp_path: Path):
    storage = LocalArtifactStorage(tmp_path)
    data = b"expected"
    checksum = hashlib.sha256(data).hexdigest()
    key = immutable_key(uuid.uuid4(), "organizer", checksum, ".tif")
    uri = storage.put(key, data, checksum)
    storage._path(uri).write_bytes(b"tampered")
    with pytest.raises(ArtifactStorageError, match="checksum"):
        storage.put(key, data, checksum)


def test_namespace_and_checksum_are_validated(tmp_path: Path):
    with pytest.raises(ArtifactStorageError):
        immutable_key("../escape", "organizer", "x" * 64, ".tif")
    with pytest.raises(ArtifactStorageError):
        immutable_key(uuid.uuid4(), "organizer", "a" * 64, ".tif/evil")


def test_missing_local_binary_fails_clearly(tmp_path: Path):
    storage = LocalArtifactStorage(tmp_path)
    with pytest.raises(ArtifactStorageError, match="missing"):
        storage.read("local://rasters/missing.tif", "a" * 64)


def test_vercel_blob_round_trip_is_private_immutable_and_verified():
    class NotFound(Exception): pass

    class FakeBlob:
        BlobNotFoundError = NotFound
        objects = {}

        @classmethod
        def _key(cls, reference):
            return reference.rsplit(".blob.vercel-storage.com/", 1)[-1]

        @classmethod
        def head(cls, reference, **kwargs):
            key = cls._key(reference)
            if key not in cls.objects:
                raise NotFound()
            return SimpleNamespace(url=f"https://test.private.blob.vercel-storage.com/{key}")

        @classmethod
        def put(cls, key, payload, **kwargs):
            assert kwargs["access"] == "private"
            assert kwargs["add_random_suffix"] is False
            assert kwargs["overwrite"] is False
            cls.objects[key] = payload
            return SimpleNamespace(url=f"https://test.private.blob.vercel-storage.com/{key}")

        @classmethod
        def get(cls, reference, **kwargs):
            assert kwargs["access"] == "private"
            return SimpleNamespace(content=cls.objects[cls._key(reference)])

    data = b"private-raster"
    checksum = hashlib.sha256(data).hexdigest()
    key = immutable_key(uuid.uuid4(), "organizer", checksum, ".tif")
    storage = VercelBlobArtifactStorage(token="test-token", store_id=None, oidc_token=None)
    storage.blob = FakeBlob
    uri = storage.put(key, data, checksum)
    assert uri.startswith("https://test.private.blob.vercel-storage.com/")
    assert storage.exists(uri)
    assert storage.read(uri, checksum) == data
    assert storage.put(key, data, checksum) == uri
    with pytest.raises(ArtifactStorageError, match="checksum"):
        storage.read(uri, "a" * 64)


def test_vercel_blob_oidc_uses_private_store_and_checksum(monkeypatch):
    import httpx

    class Response:
        def __init__(self, status_code, payload=None, content=b""):
            self.status_code = status_code
            self._payload = payload or {}
            self.content = content
            self.is_error = status_code >= 400
        def json(self): return self._payload

    data = b"oidc-raster"
    checksum = hashlib.sha256(data).hexdigest()
    key = immutable_key(uuid.uuid4(), "organizer", checksum, ".tif")
    uri = f"https://store.private.blob.vercel-storage.com/{key}"
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":
            return Response(404)
        return Response(200, {"url": uri})

    def get(url, **kwargs):
        calls.append(("BLOB_GET", url, kwargs))
        return Response(200, content=data)

    monkeypatch.setattr(httpx, "request", request)
    monkeypatch.setattr(httpx, "get", get)
    storage = VercelBlobArtifactStorage(token=None, store_id="store_abc", oidc_token="oidc-token")
    assert storage.put(key, data, checksum) == uri
    assert calls[0][2]["headers"]["x-vercel-blob-store-id"] == "abc"
    assert calls[1][2]["headers"]["x-vercel-blob-access"] == "private"
    assert storage.read(uri, checksum) == data


def test_legacy_migration_updates_metadata_only_after_verified_copy(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RASTER_STORAGE_ROOT", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()
    project_id = uuid.uuid4()
    data = b"verified-real-content"
    checksum = hashlib.sha256(data).hexdigest()
    local = LocalArtifactStorage(tmp_path)
    old_uri = local.put(immutable_key(project_id, "organizer", checksum, ".tif"), data, checksum)
    dataset = RasterDataset(id=uuid.uuid4(), project_id=project_id, source_uri=old_uri, checksum_sha256=checksum, provenance={})

    class MemoryDestination:
        objects = {}
        def put(self, key, payload, expected):
            assert hashlib.sha256(payload).hexdigest() == expected
            self.objects[key] = payload
            return f"s3://verified/{key}"
        def exists(self, uri):
            return True
        def read(self, uri, expected):
            payload = self.objects[uri.split("s3://verified/", 1)[1]]
            assert hashlib.sha256(payload).hexdigest() == expected
            return payload

    class Session:
        committed = False
        def add(self, value): pass
        def commit(self): self.committed = True
        def refresh(self, value): pass

    session = Session()
    migrated = migrate_raster_dataset(session, dataset=dataset, destination=MemoryDestination())
    assert session.committed is True
    assert migrated.source_uri.startswith("s3://verified/")
    get_settings.cache_clear()


def test_legacy_migration_does_not_commit_when_archive_checksum_is_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RASTER_STORAGE_ROOT", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()
    project_id = uuid.uuid4()
    data = b"verified-source"
    checksum = hashlib.sha256(data).hexdigest()
    local = LocalArtifactStorage(tmp_path)
    source_uri = local.put(immutable_key(project_id, "organizer", checksum, ".tif"), data, checksum)
    dataset = RasterDataset(
        id=uuid.uuid4(),
        project_id=project_id,
        source_uri=source_uri,
        checksum_sha256=checksum,
        provenance={"source_archive_uri": "local://rasters/archive.zip"},
    )

    class Session:
        committed = False
        def add(self, value): pass
        def commit(self): self.committed = True
        def refresh(self, value): pass

    session = Session()
    with pytest.raises(ArtifactStorageError, match="archive checksum is missing"):
        migrate_raster_dataset(session, dataset=dataset, destination=LocalArtifactStorage(tmp_path / "durable"))
    assert session.committed is False
    assert dataset.source_uri == source_uri
    get_settings.cache_clear()
