from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.citations import DocumentCitationReference


class DocumentSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)
    candidate_limit: int = Field(default=50, ge=5, le=200)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    version_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    document_classes: list[str] | None = Field(default=None, max_length=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("query must contain at least two non-whitespace characters")
        return cleaned

    @field_validator("document_ids", "version_ids")
    @classmethod
    def unique_ids(cls, value):
        if value is not None and len(set(value)) != len(value):
            raise ValueError("filter IDs must be unique")
        return value

    @field_validator("document_classes")
    @classmethod
    def normalize_classes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        allowed = {"RFN", "RSN", "RT", "RKK", "GPP", "CIRCULAR", "TECHNICAL_GUIDELINE", "LOCAL_AUTHORITY", "OTHER"}
        clean = [item.strip().upper() for item in value]
        if len(set(clean)) != len(clean):
            raise ValueError("document_classes must be unique")
        unknown = sorted(set(clean) - allowed)
        if unknown:
            raise ValueError(f"unsupported document classes: {', '.join(unknown)}")
        return clean


class DocumentSearchProvenance(BaseModel):
    project_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    document_page_id: uuid.UUID
    document_chunk_id: uuid.UUID
    page_number: int
    chunk_index: int
    chunk_sequence: int
    document_title: str
    document_class: str
    authority: str
    version_sequence: int
    version_label: str | None
    publication_year: int | None
    checksum_sha256: str
    chunk_text_sha256: str


class DocumentSearchHit(BaseModel):
    rank: int
    text: str
    provenance: DocumentSearchProvenance
    citation: DocumentCitationReference
    citation_label: str
    keyword_rank: int | None
    vector_rank: int | None
    keyword_score: float | None
    cosine_similarity: float | None
    fused_score: float


class DocumentSearchResponse(BaseModel):
    status: Literal["evaluated", "insufficient_evidence", "degraded"]
    search_mode: Literal["hybrid", "keyword_only"]
    query: str
    result_count: int
    hits: list[DocumentSearchHit]
    limitations: list[str]
