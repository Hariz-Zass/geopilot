from __future__ import annotations

import copy
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.raster import RasterDataset
from app.services.artifact_storage import (
    ArtifactStorage,
    ArtifactStorageError,
    LocalArtifactStorage,
    immutable_key,
)


def migrate_raster_dataset(
    session: Session,
    *,
    dataset: RasterDataset,
    destination: ArtifactStorage,
) -> RasterDataset:
    """Copy verified legacy local artifacts, then atomically update their URIs."""
    if not isinstance(dataset.id, uuid.UUID) or not isinstance(dataset.project_id, uuid.UUID):
        raise ArtifactStorageError("Raster dataset identity is invalid.")
    local = LocalArtifactStorage(Path(get_settings().raster_storage_root))
    updates: list[tuple[str, str]] = []

    def copy_one(uri: str, checksum: str) -> str:
        if not uri.startswith(local.prefix):
            return uri
        data = local.read(uri, checksum)
        suffix = Path(uri).suffix or ".bin"
        key = immutable_key(dataset.project_id, "organizer", checksum, suffix)
        durable_uri = destination.put(key, data, checksum)
        destination.read(durable_uri, checksum)
        updates.append((uri, durable_uri))
        return durable_uri

    new_source_uri = copy_one(dataset.source_uri, dataset.checksum_sha256) if dataset.source_uri else None
    provenance = copy.deepcopy(dataset.provenance or {})
    assets = provenance.get("assets") or {}
    for asset in assets.values():
        uri = str(asset.get("uri") or "")
        checksum = str(asset.get("checksum_sha256") or "")
        if uri:
            asset["uri"] = copy_one(uri, checksum)
    archive_uri = provenance.get("source_archive_uri")
    archive_checksum = provenance.get("source_archive_checksum_sha256")
    if archive_uri and not archive_checksum:
        raise ArtifactStorageError("Legacy source archive checksum is missing; migration was not committed.")
    if archive_uri:
        provenance["source_archive_uri"] = copy_one(str(archive_uri), str(archive_checksum))

    if not updates:
        raise ArtifactStorageError("Raster dataset has no legacy local artifacts to migrate.")
    dataset.source_uri = new_source_uri
    dataset.provenance = provenance
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    return dataset
