from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Iterator, Protocol
from urllib.parse import urlparse

from app.core.config import get_settings


class ArtifactStorageError(Exception):
    pass


class ArtifactStorage(Protocol):
    def put(self, key: str, data: bytes, checksum_sha256: str) -> str: ...
    def exists(self, uri: str) -> bool: ...
    def read(self, uri: str, checksum_sha256: str) -> bytes: ...


def immutable_key(project_id: object, category: str, checksum: str, suffix: str) -> str:
    if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
        raise ArtifactStorageError("Artifact checksum must be lowercase SHA-256.")
    safe_suffix = suffix.lower() if suffix.startswith(".") else f".{suffix.lower()}"
    if not safe_suffix[1:].isalnum():
        raise ArtifactStorageError("Artifact suffix is invalid.")
    parts = PurePosixPath(str(project_id), category, f"{checksum}{safe_suffix}")
    if parts.is_absolute() or ".." in parts.parts:
        raise ArtifactStorageError("Artifact key escaped its project namespace.")
    return parts.as_posix()


def _verify(data: bytes, expected: str) -> None:
    if hashlib.sha256(data).hexdigest() != expected:
        raise ArtifactStorageError("Artifact checksum verification failed.")


class LocalArtifactStorage:
    prefix = "local://rasters/"

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, uri_or_key: str) -> Path:
        key = uri_or_key[len(self.prefix):] if uri_or_key.startswith(self.prefix) else uri_or_key
        target = (self.root / key).resolve()
        if self.root != target and self.root not in target.parents:
            raise ArtifactStorageError("Artifact path escaped configured root.")
        return target

    def put(self, key: str, data: bytes, checksum_sha256: str) -> str:
        _verify(data, checksum_sha256)
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            _verify(target.read_bytes(), checksum_sha256)
        else:
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_bytes(data)
            os.replace(temporary, target)
        return self.prefix + key

    def exists(self, uri: str) -> bool:
        return self._path(uri).is_file()

    def read(self, uri: str, checksum_sha256: str) -> bytes:
        target = self._path(uri)
        if not target.is_file():
            raise ArtifactStorageError("Stored raster artifact is missing.")
        data = target.read_bytes()
        # Legacy local-only bundle metadata may predate per-asset checksums.
        # Object storage and all newly ingested artifacts always require one.
        if checksum_sha256:
            _verify(data, checksum_sha256)
        return data


class S3ArtifactStorage:
    def __init__(self, *, bucket: str, endpoint_url: str | None, region: str | None):
        if not bucket:
            raise ArtifactStorageError("ARTIFACT_S3_BUCKET is required for s3 storage.")
        try:
            import boto3
        except ImportError as exc:
            raise ArtifactStorageError("boto3 is required for s3 artifact storage.") from exc
        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url or None, region_name=region or None)

    def _key(self, uri: str) -> str:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or parsed.netloc != self.bucket:
            raise ArtifactStorageError("Artifact URI does not belong to the configured bucket.")
        key = parsed.path.lstrip("/")
        if not key or ".." in PurePosixPath(key).parts:
            raise ArtifactStorageError("Artifact object key is invalid.")
        return key

    def put(self, key: str, data: bytes, checksum_sha256: str) -> str:
        _verify(data, checksum_sha256)
        uri = f"s3://{self.bucket}/{key}"
        if self.exists(uri):
            self.read(uri, checksum_sha256)
            return uri
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, Metadata={"sha256": checksum_sha256})
        self.read(uri, checksum_sha256)
        return uri

    def exists(self, uri: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(uri))
            return True
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise ArtifactStorageError("Unable to inspect artifact object.") from exc

    def read(self, uri: str, checksum_sha256: str) -> bytes:
        if not checksum_sha256:
            raise ArtifactStorageError("Object artifact checksum is required.")
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(uri))
            data = response["Body"].read()
        except Exception as exc:
            raise ArtifactStorageError("Stored raster artifact is missing or unavailable.") from exc
        _verify(data, checksum_sha256)
        return data


class VercelBlobArtifactStorage:
    """Private Vercel Blob storage using Vercel OIDC or a read-write token."""

    api_url = "https://vercel.com/api/blob"
    api_version = "12"

    def __init__(self, *, token: str | None, store_id: str | None, oidc_token: str | None):
        self.token = token or None
        self.store_id = (store_id or "").removeprefix("store_") or None
        self.oidc_token = oidc_token or None
        if not self.token and not (self.store_id and self.oidc_token):
            raise ArtifactStorageError(
                "Vercel Blob requires BLOB_READ_WRITE_TOKEN or BLOB_STORE_ID with VERCEL_OIDC_TOKEN."
            )
        self.blob = None
        if self.token:
            try:
                import vercel.blob as blob
            except ImportError as exc:
                raise ArtifactStorageError("The official vercel Python SDK is required for token-based Vercel Blob storage.") from exc
            self.blob = blob

    @staticmethod
    def _reference(uri_or_key: str) -> str:
        parsed = urlparse(uri_or_key)
        if parsed.scheme:
            if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".blob.vercel-storage.com"):
                raise ArtifactStorageError("Artifact URI does not belong to Vercel Blob storage.")
            return uri_or_key
        path = PurePosixPath(uri_or_key)
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise ArtifactStorageError("Artifact Blob pathname is invalid.")
        return path.as_posix()

    def put(self, key: str, data: bytes, checksum_sha256: str) -> str:
        _verify(data, checksum_sha256)
        reference = self._reference(key)
        if self.exists(reference):
            self.read(reference, checksum_sha256)
            return self._url_for(reference)
        if self.oidc_token:
            response = self._oidc_api_request(
                "PUT",
                "/",
                params={"pathname": reference},
                content=data,
                headers={
                    "x-vercel-blob-access": "private",
                    "x-add-random-suffix": "0",
                    "x-allow-overwrite": "0",
                },
            )
            uri = str(response["url"])
            self.read(uri, checksum_sha256)
            return uri
        try:
            assert self.blob is not None
            result = self.blob.put(
                reference,
                data,
                access="private",
                add_random_suffix=False,
                overwrite=False,
                multipart=len(data) > 5 * 1024 * 1024,
                token=self.token,
            )
        except Exception as exc:
            raise ArtifactStorageError("Unable to store immutable artifact in Vercel Blob.") from exc
        uri = str(result.url)
        self.read(uri, checksum_sha256)
        return uri

    def exists(self, uri: str) -> bool:
        reference = self._reference(uri)
        if self.oidc_token:
            try:
                self._oidc_api_request("GET", "/", params={"url": reference})
                return True
            except ArtifactStorageError as exc:
                if str(exc) == "Stored raster artifact is missing.":
                    return False
                raise
        try:
            assert self.blob is not None
            self.blob.head(reference, token=self.token)
            return True
        except self.blob.BlobNotFoundError:
            return False
        except Exception as exc:
            raise ArtifactStorageError("Unable to inspect Vercel Blob artifact.") from exc

    def read(self, uri: str, checksum_sha256: str) -> bytes:
        if not checksum_sha256:
            raise ArtifactStorageError("Object artifact checksum is required.")
        reference = self._reference(uri)
        if self.oidc_token:
            target = self._url_for(reference)
            try:
                import httpx
                response = httpx.get(
                    target,
                    headers={"authorization": f"Bearer {self.oidc_token}"},
                    params={"cache": "0"},
                    timeout=60.0,
                )
            except httpx.HTTPError as exc:
                raise ArtifactStorageError("Stored raster artifact is unavailable from Vercel Blob.") from exc
            if response.status_code == 404:
                raise ArtifactStorageError("Stored raster artifact is missing.")
            if response.is_error:
                raise ArtifactStorageError("Stored raster artifact is unavailable from Vercel Blob.")
            data = response.content
            _verify(data, checksum_sha256)
            return data
        try:
            assert self.blob is not None
            result = self.blob.get(reference, access="private", token=self.token, use_cache=False)
            data = bytes(result.content)
        except self.blob.BlobNotFoundError as exc:
            raise ArtifactStorageError("Stored raster artifact is missing.") from exc
        except Exception as exc:
            raise ArtifactStorageError("Stored raster artifact is unavailable from Vercel Blob.") from exc
        _verify(data, checksum_sha256)
        return data

    def _url_for(self, reference: str) -> str:
        if reference.startswith("https://"):
            return reference
        if self.oidc_token:
            response = self._oidc_api_request("GET", "/", params={"url": reference})
            return str(response["url"])
        assert self.blob is not None
        return str(self.blob.head(reference, token=self.token).url)

    def _oidc_api_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str],
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        try:
            import httpx
            response = httpx.request(
                method,
                f"{self.api_url}{path}",
                params=params,
                content=content,
                headers={
                    "authorization": f"Bearer {self.oidc_token}",
                    "x-vercel-blob-store-id": str(self.store_id),
                    "x-api-version": self.api_version,
                    **(headers or {}),
                },
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            raise ArtifactStorageError("Unable to reach Vercel Blob.") from exc
        if response.status_code == 404:
            raise ArtifactStorageError("Stored raster artifact is missing.")
        if response.is_error:
            raise ArtifactStorageError("Vercel Blob rejected the artifact request.")
        try:
            return response.json()
        except ValueError as exc:
            raise ArtifactStorageError("Vercel Blob returned an invalid response.") from exc


def get_artifact_storage() -> ArtifactStorage:
    settings = get_settings()
    if settings.artifact_storage_provider == "local":
        return LocalArtifactStorage(Path(settings.raster_storage_root))
    if settings.artifact_storage_provider == "s3":
        return S3ArtifactStorage(
            bucket=settings.artifact_s3_bucket or "",
            endpoint_url=settings.artifact_s3_endpoint_url,
            region=settings.artifact_s3_region,
        )
    if settings.artifact_storage_provider == "vercel_blob":
        return VercelBlobArtifactStorage(
            token=settings.blob_read_write_token,
            store_id=settings.blob_store_id,
            oidc_token=settings.vercel_oidc_token,
        )
    raise ArtifactStorageError("Unsupported artifact storage provider.")


@contextmanager
def materialize(uri: str, checksum_sha256: str, suffix: str = ".bin") -> Iterator[Path]:
    storage = get_artifact_storage()
    if isinstance(storage, LocalArtifactStorage) and uri.startswith(storage.prefix):
        path = storage._path(uri)
        storage.read(uri, checksum_sha256)
        yield path
        return
    data = storage.read(uri, checksum_sha256)
    fd, name = tempfile.mkstemp(prefix="geopilot-artifact-", suffix=suffix)
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        yield path
    finally:
        path.unlink(missing_ok=True)
