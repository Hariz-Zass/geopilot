from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentCitationReference(BaseModel):
    """Immutable source identity carried by downstream evidence consumers.

    The reference contains identities and hashes only. Authoritative text/metadata
    is re-resolved from the database before it may be used as evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["document_citation.v1"] = "document_citation.v1"
    project_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    document_page_id: uuid.UUID
    document_chunk_id: uuid.UUID
    page_number: int = Field(ge=1)
    version_checksum_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    page_text_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    chunk_text_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class ResolvedDocumentCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: DocumentCitationReference
    status: Literal["validated"] = "validated"
    citation_label: str
    document_title: str
    document_class: str
    authority: str
    jurisdiction: str | None
    geographic_applicability: dict
    version_sequence: int
    version_label: str | None
    publication_year: int | None
    publication_date: str | None
    page_number: int
    chunk_index: int
    chunk_sequence: int
    start_char: int
    end_char: int
    text: str
    review_state: str
    limitations: list[str]


class CitationResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    references: list[DocumentCitationReference] = Field(min_length=1, max_length=100)


class CitationResolveResponse(BaseModel):
    status: Literal["validated"] = "validated"
    citations: list[ResolvedDocumentCitation]
