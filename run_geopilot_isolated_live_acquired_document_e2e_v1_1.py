from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.db import get_session_factory
from app.models.project import Project
from app.models.user import User
from app.models.planning_document import PlanningDocument, DocumentVersion
from app.schemas.document_retrieval import DocumentSearchRequest
from app.services.document_retrieval import search_documents
from app.services.planning_document_acquisition import (
    PlanMalaysiaOfficialProvider,
    acquire_candidate,
    ingest_acquired_document,
)


def resolve_owner_project(session):
    requested = os.getenv("GEOPILOT_ACCEPTANCE_PROJECT_ID", "").strip()
    if requested:
        project = session.get(Project, uuid.UUID(requested))
        if project is None:
            raise RuntimeError("GEOPILOT_ACCEPTANCE_PROJECT_ID does not exist.")
        if getattr(project, "is_archived", False):
            raise RuntimeError("Target Project is archived.")
        owner = session.get(User, project.owner_id)
        if owner is None:
            raise RuntimeError("Target Project owner does not exist.")
        return owner, project

    projects = list(
        session.scalars(
            select(Project)
            .where(Project.is_archived.is_(False))
            .order_by(Project.created_at.desc(), Project.id.desc())
        )
    )
    for project in projects:
        owner = session.get(User, project.owner_id)
        if owner is not None:
            return owner, project

    raise RuntimeError("No owned active Project is available for isolated acceptance.")


def storage_path_from_uri(uri):
    if not uri or not str(uri).startswith("local://documents/"):
        return None
    root = Path(os.getenv("DOCUMENT_STORAGE_ROOT", "/data/documents")).resolve()
    rel = str(uri)[len("local://documents/"):].lstrip("/")
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise RuntimeError("Refusing storage cleanup outside DOCUMENT_STORAGE_ROOT.")
    return target


def cleanup_storage(path):
    if path is None:
        return
    root = Path(os.getenv("DOCUMENT_STORAGE_ROOT", "/data/documents")).resolve()
    if path.exists() and path.is_file():
        path.unlink()
    parent = path.parent
    while parent != root and root in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def project_counts(session, project_id):
    docs = session.scalar(
        select(func.count())
        .select_from(PlanningDocument)
        .where(PlanningDocument.project_id == project_id)
    )
    versions = session.scalar(
        select(func.count())
        .select_from(DocumentVersion)
        .join(PlanningDocument, PlanningDocument.id == DocumentVersion.document_id)
        .where(PlanningDocument.project_id == project_id)
    )
    return int(docs or 0), int(versions or 0)


def locate_temp_version(session, project_id, checksum):
    if not checksum:
        return None
    return session.scalar(
        select(DocumentVersion)
        .join(PlanningDocument, PlanningDocument.id == DocumentVersion.document_id)
        .where(
            PlanningDocument.project_id == project_id,
            DocumentVersion.checksum_sha256 == checksum,
            DocumentVersion.provenance["acquisition_method"].as_string()
            == "planning_document_auto_ingestion_v1",
        )
        .order_by(DocumentVersion.created_at.desc())
    )


def main():
    print("=" * 72)
    print("GeoPilot Isolated Live Acquired-Document E2E Acceptance V1.1")
    print("Official GPP -> acquire -> persist -> extract -> chunks -> index -> retrieval -> cleanup")
    print("=" * 72)

    session = get_session_factory()()
    project = None
    baseline = None
    temp_document_id = None
    storage_path = None
    acquired_checksum = None

    try:
        owner, project = resolve_owner_project(session)
        print("[1] Controlled project/owner gate")
        print("project_id:", project.id)
        print("owner_id:", owner.id)

        baseline = project_counts(session, project.id)
        print("baseline_project_documents:", baseline[0])
        print("baseline_project_versions:", baseline[1])

        print("[2] Discover one official GPP")
        provider = PlanMalaysiaOfficialProvider()
        candidates = provider.discover(
            document_class="GPP",
            jurisdiction=None,
            query="tanah tinggi",
        )
        if not candidates:
            candidates = provider.discover(
                document_class="GPP",
                jurisdiction=None,
                query="",
            )
        if not candidates:
            raise RuntimeError("No official GPP candidate discovered.")
        candidate = candidates[0]
        print("candidate_title:", candidate.title)
        print("candidate_uri:", candidate.source_uri)

        print("[3] Live official PDF acquisition")
        acquired = acquire_candidate(candidate)
        acquired_checksum = acquired.checksum_sha256
        print("download_bytes:", len(acquired.content))
        print("sha256:", acquired.checksum_sha256)

        print("[4] Persist through existing auto-ingestion pipeline")
        result = ingest_acquired_document(
            session,
            owner=owner,
            project_id=project.id,
            acquired=acquired,
            build_chunks=True,
            build_index=True,
        )

        document = result["document"]
        version = result["version"]
        temp_document_id = document.id
        storage_path = storage_path_from_uri(version.storage_uri)

        print("temporary_document_id:", document.id)
        print("temporary_version_id:", version.id)
        print("source_kind:", version.source_kind)
        print("ingestion_state:", version.ingestion_state)
        print("extraction_state:", version.extraction_state)
        print("index_state:", version.index_state)
        print("review_state:", version.review_state)
        print("storage_uri:", version.storage_uri)
        print("page_count:", result["ingestion"].page_count)
        print("text_page_count:", result["ingestion"].text_page_count)
        print("requires_ocr_page_count:", result["ingestion"].requires_ocr_page_count)
        print("chunk_count:", result["chunks"].chunk_count)
        print("embedding_index_state:", result["index"].state)
        print("embedding_chunk_count:", result["index"].chunk_count)

        assert version.source_kind == "acquired"
        assert version.ingestion_state == "available"
        assert result["chunks"].chunk_count > 0
        assert result["index"].state == "ready"

        print("[5] Retrieval against acquired document only")
        response = None
        used_query = None
        for query in ("garis panduan", "tanah tinggi", "pembangunan"):
            current = search_documents(
                session,
                owner=owner,
                project_id=project.id,
                request=DocumentSearchRequest(
                    query=query,
                    top_k=5,
                    document_ids=[document.id],
                ),
            )
            if current.result_count > 0:
                response = current
                used_query = query
                break

        if response is None or response.result_count <= 0:
            raise RuntimeError("No retrieval evidence returned from temporary GPP.")

        first = response.hits[0]
        print("retrieval_query:", used_query)
        print("retrieval_status:", response.status)
        print("retrieval_mode:", response.search_mode)
        print("retrieval_result_count:", response.result_count)
        print("first_hit_document_id:", first.provenance.document_id)
        print("first_hit_page:", first.provenance.page_number)
        print("first_hit_text_preview:", " ".join(first.text.split())[:280])

        if first.provenance.document_id != document.id:
            raise RuntimeError("Retrieval escaped temporary document scope.")

        print("[6] E2E functional acceptance: PASS")
        return 0

    finally:
        print("[7] Cleanup")
        try:
            if project is not None and temp_document_id is None:
                # Recover IDs even if the pipeline failed after registration.
                try:
                    candidate_version = locate_temp_version(
                        session,
                        project.id,
                        acquired_checksum,
                    )
                except Exception:
                    session.rollback()
                    candidate_version = session.scalar(
                        select(DocumentVersion)
                        .join(
                            PlanningDocument,
                            PlanningDocument.id == DocumentVersion.document_id,
                        )
                        .where(
                            PlanningDocument.project_id == project.id,
                            DocumentVersion.checksum_sha256 == acquired_checksum,
                        )
                        .order_by(DocumentVersion.created_at.desc())
                    ) if acquired_checksum else None

                if candidate_version is not None:
                    temp_document_id = candidate_version.document_id
                    storage_path = storage_path_from_uri(candidate_version.storage_uri)

            if temp_document_id is not None:
                obj = session.get(PlanningDocument, temp_document_id)
                if obj is not None:
                    if storage_path is None and obj.versions:
                        storage_path = storage_path_from_uri(
                            obj.versions[0].storage_uri
                        )
                    session.delete(obj)
                    session.commit()
                    print("temporary_document_db_cleanup: PASS")
                else:
                    print("temporary_document_db_cleanup: already absent")
            else:
                session.rollback()
                print("temporary_document_db_cleanup: no row created")

            cleanup_storage(storage_path)
            if storage_path is not None:
                print(
                    "temporary_storage_cleanup:",
                    "PASS" if not storage_path.exists() else "FAIL",
                )

            if project is not None and baseline is not None:
                final = project_counts(session, project.id)
                print("final_project_documents:", final[0])
                print("final_project_versions:", final[1])
                restored = final == baseline
                print("project_counts_restored:", "PASS" if restored else "FAIL")
                if not restored:
                    raise RuntimeError("Project document/version counts were not restored.")
        finally:
            session.close()


if __name__ == "__main__":
    sys.exit(main())
