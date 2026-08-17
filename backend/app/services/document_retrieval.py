from __future__ import annotations

import math
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.planning_document import (
    DocumentChunk,
    DocumentChunkEmbedding,
    DocumentEmbeddingIndex,
    DocumentPage,
    DocumentVersion,
    PlanningDocument,
)
from app.models.user import User
from app.schemas.document_retrieval import (
    DocumentSearchHit,
    DocumentSearchProvenance,
    DocumentSearchRequest,
    DocumentSearchResponse,
)
from app.services.citations import build_citation_reference
from app.services.embedding_providers import (
    EmbeddingProviderError,
    build_provider,
)
from app.services.isolation import (
    ProjectScopeNotFoundError,
    ProjectState,
    ScopeStateError,
    resolve_project_scope,
)


RRF_K = 60

# Keyword evidence gets a small advantage over semantic similarity.
# Vector retrieval is still retained for multilingual / semantic matching.
KEYWORD_WEIGHT = 1.35
VECTOR_WEIGHT = 1.0

_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


# Planning-domain concepts used only for reranking retrieved evidence.
# These do NOT contain planning answers or policy values.
_QUERY_CONCEPTS: dict[str, tuple[str, ...]] = {
    "density": (
        "density",
        "densiti",
        "kepadatan",
        "unit/hektar",
        "unit / hektar",
        "unit/ha",
        "unit / ha",
        "unit/ekar",
        "unit / ekar",
        "unit/acre",
        "unit / acre",
    ),
    "plot_ratio": (
        "plot ratio",
        "nisbah plot",
    ),
    "setback": (
        "setback",
        "anjakan",
        "jarak bangunan",
    ),
    "height": (
        "building height",
        "height",
        "ketinggian bangunan",
        "ketinggian",
    ),
    "parking": (
        "parking",
        "car park",
        "tempat letak kereta",
        "tlk",
    ),
}


_QUERY_CONCEPT_TRIGGERS: dict[str, tuple[str, ...]] = {
    "density": (
        "density",
        "densiti",
        "kepadatan",
    ),
    "plot_ratio": (
        "plot ratio",
        "nisbah plot",
    ),
    "setback": (
        "setback",
        "anjakan",
    ),
    "height": (
        "building height",
        "ketinggian bangunan",
    ),
    "parking": (
        "parking",
        "tempat letak kereta",
        "tlk",
    ),
}


class DocumentRetrievalProjectNotFoundError(Exception):
    pass


class DocumentRetrievalStateError(Exception):
    pass


@dataclass(frozen=True)
class _Candidate:
    chunk_id: uuid.UUID
    score: float


def _active_project(
    session: Session,
    owner: User,
    project_id: uuid.UUID,
) -> None:
    try:
        resolve_project_scope(
            session,
            owner=owner,
            project_id=project_id,
            state=ProjectState.ACTIVE,
        )
    except ProjectScopeNotFoundError as exc:
        raise DocumentRetrievalProjectNotFoundError from exc
    except ScopeStateError as exc:
        raise DocumentRetrievalStateError(str(exc)) from exc


def _base_rows(
    session: Session,
    project_id: uuid.UUID,
    request: DocumentSearchRequest,
):
    stmt = (
        select(
            DocumentChunk,
            DocumentPage,
            DocumentVersion,
            PlanningDocument,
        )
        .join(
            DocumentPage,
            DocumentPage.id == DocumentChunk.document_page_id,
        )
        .join(
            DocumentVersion,
            DocumentVersion.id == DocumentChunk.document_version_id,
        )
        .join(
            PlanningDocument,
            PlanningDocument.id == DocumentVersion.document_id,
        )
        .where(
            PlanningDocument.project_id == project_id,
            PlanningDocument.is_archived.is_(False),
            DocumentVersion.extraction_state.in_(
                ["ready", "requires_review"]
            ),
        )
    )

    if request.document_ids:
        stmt = stmt.where(
            PlanningDocument.id.in_(request.document_ids)
        )

    if request.version_ids:
        stmt = stmt.where(
            DocumentVersion.id.in_(request.version_ids)
        )

    if request.document_classes:
        stmt = stmt.where(
            PlanningDocument.document_class.in_(
                request.document_classes
            )
        )

    return list(
        session.execute(
            stmt.order_by(DocumentChunk.id.asc())
        )
    )


def _tokens(value: str) -> list[str]:
    return [
        item.casefold()
        for item in _TOKEN_RE.findall(value)
        if len(item) > 1
    ]


def _query_concepts(query: str) -> set[str]:
    lowered = query.casefold()

    concepts: set[str] = set()

    for concept, triggers in _QUERY_CONCEPT_TRIGGERS.items():
        if any(trigger in lowered for trigger in triggers):
            concepts.add(concept)

    return concepts


def _concept_relevance_bonus(
    query: str,
    chunk_text: str,
) -> float:
    """
    Add a bounded planning-domain relevance bonus.

    This does not fabricate planning values. It only promotes
    already-retrieved chunks that contain terminology directly
    related to the concept in the user's question.
    """
    concepts = _query_concepts(query)

    if not concepts:
        return 0.0

    lowered = chunk_text.casefold()
    bonus = 0.0

    for concept in concepts:
        terms = _QUERY_CONCEPTS.get(concept, ())

        matched_terms = {
            term
            for term in terms
            if term in lowered
        }

        if matched_terms:
            bonus += 0.020

        bonus += min(
            len(matched_terms),
            4,
        ) * 0.006

        if concept == "density":
            has_density_word = any(
                term in lowered
                for term in (
                    "density",
                    "densiti",
                    "kepadatan",
                )
            )

            has_density_unit = any(
                term in lowered
                for term in (
                    "unit/hektar",
                    "unit / hektar",
                    "unit/ha",
                    "unit / ha",
                    "unit/ekar",
                    "unit / ekar",
                    "unit/acre",
                    "unit / acre",
                )
            )

            has_numeric_density_value = bool(
                re.search(
                    r"\b\d+(?:\.\d+)?"
                    r"(?:\s*[-–]\s*\d+(?:\.\d+)?)?"
                    r"\s*(?:unit\s*/?\s*"
                    r"(?:hektar|ha|ekar|acre))",
                    lowered,
                )
            )

            if has_density_word and has_density_unit:
                bonus += 0.025

            if has_numeric_density_value:
                bonus += 0.030

    return bonus


def _keyword_python(
    rows,
    query: str,
    limit: int,
) -> list[_Candidate]:
    terms = _tokens(query)

    if not terms:
        return []

    query_phrase = query.casefold()
    scored: list[_Candidate] = []

    for chunk, _page, _version, _document in rows:
        lowered = chunk.text.casefold()

        token_counts = {
            term: lowered.count(term)
            for term in set(terms)
        }

        matched = sum(
            1
            for term in terms
            if token_counts.get(term, 0) > 0
        )

        if matched == 0:
            continue

        coverage = matched / len(terms)

        frequency = (
            sum(token_counts.values())
            / max(1, len(terms))
        )

        phrase_bonus = (
            1.0
            if query_phrase in lowered
            else 0.0
        )

        score = (
            coverage
            + min(frequency, 10.0) * 0.05
            + phrase_bonus
        )

        scored.append(
            _Candidate(
                chunk.id,
                score,
            )
        )

    scored.sort(
        key=lambda item: (
            -item.score,
            str(item.chunk_id),
        )
    )

    return scored[:limit]


def _vector_python(
    session: Session,
    rows,
    query_vector: list[float],
    index_id: uuid.UUID,
    limit: int,
) -> list[_Candidate]:
    allowed = {
        row[0].id
        for row in rows
    }

    embeddings = list(
        session.scalars(
            select(DocumentChunkEmbedding).where(
                DocumentChunkEmbedding.embedding_index_id
                == index_id
            )
        )
    )

    qnorm = math.sqrt(
        sum(v * v for v in query_vector)
    )

    if qnorm == 0:
        return []

    scored: list[_Candidate] = []

    for emb in embeddings:
        if (
            emb.document_chunk_id not in allowed
            or len(emb.embedding) != len(query_vector)
        ):
            continue

        current = next(
            (
                row[0]
                for row in rows
                if row[0].id
                == emb.document_chunk_id
            ),
            None,
        )

        if (
            current is None
            or emb.text_sha256
            != current.text_sha256
        ):
            continue

        enorm = math.sqrt(
            sum(v * v for v in emb.embedding)
        )

        if enorm == 0:
            continue

        cosine = sum(
            a * b
            for a, b in zip(
                query_vector,
                emb.embedding,
                strict=True,
            )
        ) / (qnorm * enorm)

        scored.append(
            _Candidate(
                emb.document_chunk_id,
                max(
                    -1.0,
                    min(1.0, cosine),
                ),
            )
        )

    scored.sort(
        key=lambda item: (
            -item.score,
            str(item.chunk_id),
        )
    )

    return scored[:limit]


def _keyword_postgres(
    session: Session,
    project_id: uuid.UUID,
    request: DocumentSearchRequest,
) -> list[_Candidate]:
    filters = [
        "d.project_id = :project_id",
        "d.is_archived = false",
        (
            "v.extraction_state IN "
            "('ready','requires_review')"
        ),
    ]

    params: dict[str, object] = {
        "project_id": str(project_id),
        "query": request.query,
        "limit": request.candidate_limit,
    }

    if request.document_ids:
        filters.append(
            "d.id = ANY(CAST(:document_ids AS uuid[]))"
        )
        params["document_ids"] = [
            str(value)
            for value in request.document_ids
        ]

    if request.version_ids:
        filters.append(
            "v.id = ANY(CAST(:version_ids AS uuid[]))"
        )
        params["version_ids"] = [
            str(value)
            for value in request.version_ids
        ]

    if request.document_classes:
        filters.append(
            (
                "d.document_class = "
                "ANY(CAST(:document_classes AS text[]))"
            )
        )
        params["document_classes"] = (
            request.document_classes
        )

    sql = text(
        f"""
        WITH q AS (
            SELECT websearch_to_tsquery(
                'simple',
                :query
            ) AS query
        )
        SELECT
            c.id,
            ts_rank_cd(
                to_tsvector('simple', c.text),
                q.query,
                32
            ) AS score
        FROM document_chunks c
        JOIN document_versions v
            ON v.id = c.document_version_id
        JOIN planning_documents d
            ON d.id = v.document_id
        CROSS JOIN q
        WHERE {' AND '.join(filters)}
          AND to_tsvector(
              'simple',
              c.text
          ) @@ q.query
        ORDER BY
            score DESC,
            c.id ASC
        LIMIT :limit
        """
    )

    return [
        _Candidate(
            uuid.UUID(str(row[0])),
            float(row[1]),
        )
        for row in session.execute(
            sql,
            params,
        )
    ]


def _vector_postgres(
    session: Session,
    rows,
    query_vector: list[float],
    index_id: uuid.UUID,
    limit: int,
) -> list[_Candidate]:
    allowed = [
        str(row[0].id)
        for row in rows
    ]

    if not allowed:
        return []

    vector_literal = (
        "["
        + ",".join(
            format(float(v), ".17g")
            for v in query_vector
        )
        + "]"
    )

    sql = text(
        """
        SELECT
            e.document_chunk_id,
            1.0 - (
                e.embedding
                <=> CAST(:query_vector AS vector)
            ) AS cosine_similarity
        FROM document_chunk_embeddings e
        JOIN document_chunks c
            ON c.id = e.document_chunk_id
        WHERE e.embedding_index_id = :index_id
          AND e.document_chunk_id
              = ANY(CAST(:chunk_ids AS uuid[]))
          AND e.text_sha256 = c.text_sha256
        ORDER BY
            e.embedding
                <=> CAST(:query_vector AS vector),
            e.document_chunk_id ASC
        LIMIT :limit
        """
    )

    params = {
        "query_vector": vector_literal,
        "index_id": str(index_id),
        "chunk_ids": allowed,
        "limit": limit,
    }

    return [
        _Candidate(
            uuid.UUID(str(row[0])),
            float(row[1]),
        )
        for row in session.execute(
            sql,
            params,
        )
    ]


def _ready_indexes(
    session: Session,
    version_ids: Iterable[uuid.UUID],
) -> list[DocumentEmbeddingIndex]:
    ids = list(version_ids)

    if not ids:
        return []

    return list(
        session.scalars(
            select(DocumentEmbeddingIndex)
            .join(
                DocumentVersion,
                DocumentVersion.id
                == DocumentEmbeddingIndex.document_version_id,
            )
            .where(
                DocumentEmbeddingIndex.document_version_id.in_(
                    ids
                ),
                DocumentEmbeddingIndex.state == "ready",
                DocumentVersion.index_state == "ready",
            )
            .order_by(
                DocumentEmbeddingIndex.document_version_id.asc(),
                DocumentEmbeddingIndex.created_at.desc(),
                DocumentEmbeddingIndex.id.asc(),
            )
        )
    )


def _query_vector_for_index(
    index: DocumentEmbeddingIndex,
    query: str,
) -> list[float]:
    provider = build_provider(index.provider)
    batch = provider.embed([query])

    if (
        batch.provider != index.provider
        or batch.model_name != index.model_name
    ):
        raise EmbeddingProviderError(
            (
                "query embedding provider/model does "
                "not match persisted index"
            )
        )

    if batch.model_revision != index.model_revision:
        raise EmbeddingProviderError(
            (
                "query embedding model revision does "
                "not match persisted index"
            )
        )

    if (
        len(batch.vectors) != 1
        or len(batch.vectors[0])
        != index.dimensions
    ):
        raise EmbeddingProviderError(
            (
                "query embedding dimensions do not "
                "match persisted index"
            )
        )

    return batch.vectors[0]


def search_documents(
    session: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    request: DocumentSearchRequest,
) -> DocumentSearchResponse:
    _active_project(
        session,
        owner,
        project_id,
    )

    rows = _base_rows(
        session,
        project_id,
        request,
    )

    if not rows:
        return DocumentSearchResponse(
            status="insufficient_evidence",
            search_mode="keyword_only",
            query=request.query,
            result_count=0,
            hits=[],
            limitations=[
                (
                    "No eligible document chunks matched "
                    "the requested project/filter scope."
                )
            ],
        )

    dialect = session.get_bind().dialect.name

    keyword = (
        _keyword_postgres(
            session,
            project_id,
            request,
        )
        if dialect == "postgresql"
        else _keyword_python(
            rows,
            request.query,
            request.candidate_limit,
        )
    )

    version_ids = {
        row[2].id
        for row in rows
    }

    indexes = _ready_indexes(
        session,
        version_ids,
    )

    # One ready index per document version is authoritative.
    # If historical indexes coexist, deterministic ordering
    # selects the most recent ready index.
    selected: dict[
        uuid.UUID,
        DocumentEmbeddingIndex,
    ] = {}

    for idx in indexes:
        selected.setdefault(
            idx.document_version_id,
            idx,
        )

    vector_scores: dict[
        uuid.UUID,
        float,
    ] = {}

    vector_errors: list[str] = []

    for index in selected.values():
        try:
            query_vector = _query_vector_for_index(
                index,
                request.query,
            )

            index_rows = [
                row
                for row in rows
                if row[2].id
                == index.document_version_id
            ]

            candidates = (
                _vector_postgres(
                    session,
                    index_rows,
                    query_vector,
                    index.id,
                    request.candidate_limit,
                )
                if dialect == "postgresql"
                else _vector_python(
                    session,
                    index_rows,
                    query_vector,
                    index.id,
                    request.candidate_limit,
                )
            )

            for candidate in candidates:
                vector_scores[candidate.chunk_id] = max(
                    vector_scores.get(
                        candidate.chunk_id,
                        -1.0,
                    ),
                    candidate.score,
                )

        except EmbeddingProviderError as exc:
            vector_errors.append(
                (
                    "Vector retrieval unavailable for "
                    f"version {index.document_version_id}: "
                    f"{exc}"
                )
            )

    keyword_rank = {
        candidate.chunk_id: rank
        for rank, candidate in enumerate(
            keyword,
            start=1,
        )
    }

    keyword_score = {
        candidate.chunk_id: candidate.score
        for candidate in keyword
    }

    vector_ordered = sorted(
        vector_scores.items(),
        key=lambda item: (
            -item[1],
            str(item[0]),
        ),
    )[: request.candidate_limit]

    vector_rank = {
        chunk_id: rank
        for rank, (
            chunk_id,
            _score,
        ) in enumerate(
            vector_ordered,
            start=1,
        )
    }

    candidate_ids = (
        set(keyword_rank)
        | set(vector_rank)
    )

    if not candidate_ids:
        limitations = (
            vector_errors
            or [
                (
                    "No relevant document evidence "
                    "was retrieved for this query."
                )
            ]
        )

        return DocumentSearchResponse(
            status="insufficient_evidence",
            search_mode=(
                "keyword_only"
                if not vector_rank
                else "hybrid"
            ),
            query=request.query,
            result_count=0,
            hits=[],
            limitations=limitations,
        )

    row_by_chunk = {
        row[0].id: row
        for row in rows
    }

    fused: list[
        tuple[uuid.UUID, float]
    ] = []

    for chunk_id in candidate_ids:
        score = 0.0

        if chunk_id in keyword_rank:
            score += (
                KEYWORD_WEIGHT
                / (
                    RRF_K
                    + keyword_rank[chunk_id]
                )
            )

        if chunk_id in vector_rank:
            score += (
                VECTOR_WEIGHT
                / (
                    RRF_K
                    + vector_rank[chunk_id]
                )
            )

        row = row_by_chunk.get(chunk_id)

        if row is not None:
            chunk = row[0]

            score += _concept_relevance_bonus(
                request.query,
                chunk.text,
            )

        fused.append(
            (
                chunk_id,
                score,
            )
        )

    fused.sort(
        key=lambda item: (
            -item[1],
            str(item[0]),
        )
    )

    hits: list[
        DocumentSearchHit
    ] = []

    for final_rank, (
        chunk_id,
        fused_score,
    ) in enumerate(
        fused[: request.top_k],
        start=1,
    ):
        (
            chunk,
            page,
            version,
            document,
        ) = row_by_chunk[chunk_id]

        citation = build_citation_reference(
            project_id=project_id,
            document=document,
            version=version,
            page=page,
            chunk=chunk,
        )

        citation_label = (
            f"{document.title}"
            f"{', ' + version.version_label.strip() if version.version_label and version.version_label.strip() else ''}"
            f", p. {page.page_number}"
        )

        hits.append(
            DocumentSearchHit(
                rank=final_rank,
                text=chunk.text,
                provenance=DocumentSearchProvenance(
                    project_id=project_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    document_page_id=page.id,
                    document_chunk_id=chunk.id,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    chunk_sequence=chunk.chunk_sequence,
                    document_title=document.title,
                    document_class=document.document_class,
                    authority=document.authority,
                    version_sequence=version.version_sequence,
                    version_label=version.version_label,
                    publication_year=version.publication_year,
                    checksum_sha256=version.checksum_sha256,
                    chunk_text_sha256=chunk.text_sha256,
                ),
                citation=citation,
                citation_label=citation_label,
                keyword_rank=keyword_rank.get(
                    chunk_id
                ),
                vector_rank=vector_rank.get(
                    chunk_id
                ),
                keyword_score=keyword_score.get(
                    chunk_id
                ),
                cosine_similarity=vector_scores.get(
                    chunk_id
                ),
                fused_score=fused_score,
            )
        )

    hybrid = bool(vector_rank)

    limitations = list(
        vector_errors
    )

    if not hybrid:
        limitations.append(
            (
                "Vector retrieval was unavailable or "
                "no ready embedding index existed; "
                "results are keyword-only."
            )
        )

    status = (
        "degraded"
        if limitations
        else "evaluated"
    )

    return DocumentSearchResponse(
        status=status,
        search_mode=(
            "hybrid"
            if hybrid
            else "keyword_only"
        ),
        query=request.query,
        result_count=len(hits),
        hits=hits,
        limitations=limitations,
    )