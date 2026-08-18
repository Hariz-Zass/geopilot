from __future__ import annotations

import os
import shutil
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
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
        owner_id = getattr(project, "owner_id", None)
        if owner_id is None:
            raise RuntimeError("Target Project has no owner_id attribute.")
        owner = session.get(User, owner_id)
        if owner is None:
            raise RuntimeError("Target Project owner does not exist.")
        return owner, project

    projects = list(session.scalars(select(Project)))
    if not projects:
        raise RuntimeError("No existing Project is available for isolated acceptance.")

    for project in projects:
        owner_id = getattr(project, "owner_id", None)
        if owner_id is None:
            continue
        owner = session.get(User, owner_id)
        if owner is None:
            continue

        # Prefer an obviously active project when such fields exist.
        if hasattr(project, "is_archived") and bool(getattr(project, "is_archived")):
            continue
        if hasattr(project, "status"):
            status = str(getattr(project, "status") or "").casefold()
            if status in {"archived", "inactive", "deleted"}:
                continue
        return owner, project

    raise RuntimeError("No owned active Project could be resolved safely.")


def storage_path_from_uri(uri: str | None) -> Path | None:
    if not uri or not uri.startswith("local://documents/"):
        return None
    root = Path(os.getenv("DOCUMENT_STORAGE_ROOT", "/data/documents")).resolve()
    rel = uri[len("local://documents/"):].lstrip("/")
    target = (root / rel).resolve()
    if root != target and root not in target.parents:
        raise RuntimeError("Refusing to clean a document path outside DOCUMENT_STORAGE_ROOT.")
    return target


def cleanup_storage(path: Path | None):
    if path is None:
        return
    if path.exists():
        path.unlink()
    # Remove only empty parent directories beneath DOCUMENT_STORAGE_ROOT.
    root = Path(os.getenv("DOCUMENT_STORAGE_ROOT", "/data/documents")).resolve()
    parent = path.parent
    while parent != root and root in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def main() -> int:
    print("=" * 72)
    print("GeoPilot Isolated Live Acquired-Document E2E Acceptance V1")
    print("Official GPP -> acquire -> DB ingest -> extract -> chunks -> index -> retrieval -> cleanup")
    print("=" * 72)

    session = SessionLocal()
    temp_document_id = None
    temp_version_id = None
    storage_path = None
    baseline_docs = None
    baseline_versions = None

    try:
        owner, project = resolve_owner_project(session)
        print("[1] Controlled project/owner gate")
        print("project_id:", project.id)
        print("owner_id:", owner.id)

        baseline_docs = session.scalar(
            select(__import__("sqlalchemy").func.count())
            .select_from(PlanningDocument)
            .where(PlanningDocument.project_id == project.id)
        )
        baseline_versions = session.scalar(
            select(__import__("sqlalchemy").func.count())
            .select_from(DocumentVersion)
            .join(PlanningDocument, PlanningDocument.id == DocumentVersion.document_id)
            .where(PlanningDocument.project_id == project.id)
        )
        print("baseline_project_documents:", baseline_docs)
        print("baseline_project_versions:", baseline_versions)

        print("[2] Discover one official GPP candidate")
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
            raise RuntimeError("No official GPP candidate was discovered.")

        candidate = candidates[0]
        print("candidate_title:", candidate.title)
        print("candidate_uri:", candidate.source_uri)

        print("[3] Live official PDF acquisition")
        acquired = acquire_candidate(candidate)
        print("download_bytes:", len(acquired.content))
        print("sha256:", acquired.checksum_sha256)
        print("final_uri:", acquired.final_uri)

        print("[4] Persist through existing GeoPilot document pipeline")
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
        temp_version_id = version.id
        storage_path = storage_path_from_uri(getattr(version, "storage_uri", None))

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

        if version.source_kind != "acquired":
            raise RuntimeError("Persisted version did not retain source_kind=acquired.")
        if version.ingestion_state != "available":
            raise RuntimeError("Persisted acquired PDF is not available.")
        if result["chunks"].chunk_count <= 0:
            raise RuntimeError("Acquired document produced no searchable chunks.")
        if result["index"].state != "ready":
            raise RuntimeError("Acquired document embedding index is not ready.")

        print("[5] Retrieval against temporary acquired document")
        search_terms = [
            "garis panduan",
            "tanah tinggi",
            "pembangunan",
        ]
        response = None
        used_query = None
        for query in search_terms:
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
            raise RuntimeError("Document retrieval returned no evidence from the acquired GPP.")

        print("retrieval_query:", used_query)
        print("retrieval_status:", response.status)
        print("retrieval_mode:", response.search_mode)
        print("retrieval_result_count:", response.result_count)
        first = response.hits[0]
        print("first_hit_document_id:", first.provenance.document_id)
        print("first_hit_page:", first.provenance.page_number)
        print("first_hit_citation_label:", first.citation_label)
        print("first_hit_text_preview:", " ".join(first.text.split())[:280])

        if first.provenance.document_id != document.id:
            raise RuntimeError("Retrieval escaped temporary acquired document scope.")

        print("[6] E2E functional acceptance: PASS")

        return 0

    finally:
        print("[7] Cleanup")
        try:
            if temp_document_id is not None:
                obj = session.get(PlanningDocument, temp_document_id)
                if obj is not None:
                    session.delete(obj)
                    session.commit()
                    print("temporary_document_db_cleanup: PASS")
                else:
                    print("temporary_document_db_cleanup: already absent")
            else:
                session.rollback()
                print("temporary_document_db_cleanup: no row created")
        except Exception as exc:
            session.rollback()
            print("temporary_document_db_cleanup: FAIL", type(exc).__name__, str(exc))
            raise
        finally:
            try:
                cleanup_storage(storage_path)
                if storage_path is not None:
                    print("temporary_storage_cleanup:", "PASS" if not storage_path.exists() else "FAIL")
            finally:
                if baseline_docs is not None:
                    final_docs = session.scalar(
                        select(__import__("sqlalchemy").func.count())
                        .select_from(PlanningDocument)
                        .where(PlanningDocument.project_id == project.id)
                    )
                    final_versions = session.scalar(
                        select(__import__("sqlalchemy").func.count())
                        .select_from(DocumentVersion)
                        .join(PlanningDocument, PlanningDocument.id == DocumentVersion.document_id)
                        .where(PlanningDocument.project_id == project.id)
                    )
                    print("final_project_documents:", final_docs)
                    print("final_project_versions:", final_versions)
                    print(
                        "project_counts_restored:",
                        "PASS"
                        if final_docs == baseline_docs and final_versions == baseline_versions
                        else "FAIL",
                    )
                session.close()


if __name__ == "__main__":
    sys.exit(main())
