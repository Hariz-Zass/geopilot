from pathlib import Path

service = Path("/app/app/services/planning_document_acquisition.py")
text = service.read_text(encoding="utf-8-sig")

if "def register_acquired_document" in text and "def ingest_acquired_document" in text:
    print("SKIP: Auto-ingestion pipeline V1.1 already present.")
    raise SystemExit(0)

append = """
from app.schemas.planning_document import PlanningDocumentCreateRequest
from app.services.document_chunking import build_document_chunks
from app.services.document_indexing import build_document_embedding_index
from app.services.pdf_ingestion import ingest_registered_pdf
from app.services.planning_documents import create_planning_document


class PlanningDocumentAutoIngestionError(Exception):
    pass


def _safe_source_filename(candidate: PlanningDocumentCandidate) -> str:
    name = urlparse(candidate.source_uri).path.rsplit("/", 1)[-1] or "acquired.pdf"
    if not name.casefold().endswith(".pdf"):
        name += ".pdf"
    return name[:255]


def register_acquired_document(session, *, owner, project_id, acquired):
    candidate = acquired.candidate
    provenance = {
        "provider": candidate.provider,
        "authority": candidate.authority,
        "source_uri": candidate.source_uri,
        "final_uri": acquired.final_uri,
        "discovery_metadata": dict(candidate.metadata or {}),
        "acquisition_method": "planning_document_auto_ingestion_v1",
        "checksum_sha256": acquired.checksum_sha256,
        "statutory_effect_verified": bool(
            (candidate.metadata or {}).get("statutory_effect_verified", False)
        ),
        "document_status": (candidate.metadata or {}).get(
            "document_status", "unverified"
        ),
    }

    request = PlanningDocumentCreateRequest(
        title=candidate.title,
        document_class=candidate.document_class,
        authority=candidate.authority,
        jurisdiction=candidate.jurisdiction,
        geographic_applicability={},
        initial_version={
            "source_kind": "acquired",
            "source_filename": _safe_source_filename(candidate),
            "source_uri": acquired.final_uri,
            "mime_type": acquired.mime_type,
            "file_size_bytes": len(acquired.content),
            "checksum_sha256": acquired.checksum_sha256,
            "ingestion_state": "registered",
            "extraction_state": "pending",
            "index_state": "pending",
            "review_state": "requires_review",
            "provenance": provenance,
        },
    )

    return create_planning_document(
        session,
        owner=owner,
        project_id=project_id,
        request=request,
    )


def ingest_acquired_document(
    session,
    *,
    owner,
    project_id,
    acquired,
    build_chunks=True,
    build_index=True,
):
    document, version = register_acquired_document(
        session,
        owner=owner,
        project_id=project_id,
        acquired=acquired,
    )

    ingestion = ingest_registered_pdf(
        session,
        owner=owner,
        project_id=project_id,
        document_id=document.id,
        version_id=version.id,
        filename=_safe_source_filename(acquired.candidate),
        content_type=acquired.mime_type,
        data=acquired.content,
    )

    chunk_summary = None
    index = None

    if build_chunks:
        chunk_summary = build_document_chunks(
            session,
            owner=owner,
            project_id=project_id,
            document_id=document.id,
            version_id=version.id,
        )

    if build_index:
        if not build_chunks:
            raise PlanningDocumentAutoIngestionError(
                "Embedding index creation requires chunking in V1."
            )
        index = build_document_embedding_index(
            session,
            owner=owner,
            project_id=project_id,
            document_id=document.id,
            version_id=version.id,
        )

    return {
        "document": document,
        "version": ingestion.version,
        "ingestion": ingestion,
        "chunks": chunk_summary,
        "index": index,
    }
"""

service.write_text(text.rstrip() + "\n\n" + append.strip() + "\n", encoding="utf-8")
print("PATCHED:", service)
