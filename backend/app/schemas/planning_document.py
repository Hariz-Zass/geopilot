from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DocumentClass = Literal["RFN", "RSN", "RT", "RKK", "GPP", "CIRCULAR", "TECHNICAL_GUIDELINE", "LOCAL_AUTHORITY", "OTHER"]
DocumentSourceKind = Literal["upload", "acquired", "external_reference"]
IngestionState = Literal["registered", "available", "failed"]
ExtractionState = Literal["pending", "ready", "failed", "requires_review"]
IndexState = Literal["pending", "ready", "failed"]
ReviewState = Literal["unreviewed", "reviewed", "requires_review"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class DocumentVersionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_label: str | None = Field(default=None, max_length=120)
    publication_year: int | None = Field(default=None, ge=1900, le=2200)
    publication_date: date | None = None
    source_kind: DocumentSourceKind
    source_filename: str | None = Field(default=None, max_length=255)
    source_uri: str | None = Field(default=None, max_length=4096)
    storage_uri: str | None = Field(default=None, max_length=4096)
    mime_type: str = Field(default="application/pdf", min_length=3, max_length=120)
    file_size_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str = Field(min_length=64, max_length=64)
    ingestion_state: IngestionState = "registered"
    extraction_state: ExtractionState = "pending"
    index_state: IndexState = "pending"
    review_state: ReviewState = "unreviewed"
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("version_label", "source_filename", "source_uri", "storage_uri")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("mime_type")
    @classmethod
    def normalize_mime(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("checksum_sha256")
    @classmethod
    def checksum(cls, value: str) -> str:
        value = value.strip().lower()
        if not _SHA256.fullmatch(value):
            raise ValueError("checksum_sha256 must be 64 hexadecimal characters")
        return value

    @model_validator(mode="after")
    def source_identity(self):
        if self.source_kind == "upload" and not self.source_filename:
            raise ValueError("upload document versions require source_filename")
        if self.source_kind in {"acquired", "external_reference"} and not self.source_uri:
            raise ValueError(f"{self.source_kind} document versions require source_uri")
        if self.publication_date is not None:
            if self.publication_year is None:
                self.publication_year = self.publication_date.year
            elif self.publication_year != self.publication_date.year:
                raise ValueError("publication_year must match publication_date")
        return self


class PlanningDocumentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    document_class: DocumentClass
    authority: str = Field(min_length=1, max_length=255)
    jurisdiction: str | None = Field(default=None, max_length=255)
    geographic_applicability: dict[str, Any] = Field(default_factory=dict)
    initial_version: DocumentVersionCreateRequest

    @field_validator("title", "authority")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        result = _clean(value)
        if result is None:
            raise ValueError("value must not be blank")
        return result

    @field_validator("description", "jurisdiction")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        return _clean(value)


class PlanningDocumentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    jurisdiction: str | None = Field(default=None, max_length=255)
    geographic_applicability: dict[str, Any] | None = None
    is_archived: bool | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        result = _clean(value)
        if result is None:
            raise ValueError("title must not be blank")
        return result

    @field_validator("description", "jurisdiction")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        return _clean(value)


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    version_sequence: int
    version_label: str | None
    publication_year: int | None
    publication_date: date | None
    source_kind: str
    source_filename: str | None
    source_uri: str | None
    storage_uri: str | None
    mime_type: str
    file_size_bytes: int | None
    checksum_sha256: str
    ingestion_state: str
    extraction_state: str
    index_state: str
    review_state: str
    provenance: dict[str, Any]
    created_at: datetime


class PlanningDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    document_class: str
    authority: str
    jurisdiction: str | None
    geographic_applicability: dict[str, Any]
    is_archived: bool
    created_at: datetime
    updated_at: datetime

class DocumentPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_version_id: uuid.UUID
    page_number: int
    extracted_text: str
    text_sha256: str
    char_count: int
    extraction_method: str
    extraction_state: str
    requires_ocr: bool
    created_at: datetime


class PdfIngestionResponse(BaseModel):
    version: DocumentVersionResponse
    page_count: int
    text_page_count: int
    requires_ocr_page_count: int
    extraction_state: str
    review_state: str


class DocumentChunkBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_chars: int = Field(default=1200, ge=256, le=8000)
    overlap_chars: int = Field(default=200, ge=0, le=4000)

    @model_validator(mode="after")
    def validate_overlap(self):
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")
        if self.overlap_chars > self.max_chars // 2:
            raise ValueError("overlap_chars must not exceed half of max_chars")
        return self


class DocumentChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_version_id: uuid.UUID
    document_page_id: uuid.UUID
    page_number: int
    chunk_index: int
    chunk_sequence: int
    start_char: int
    end_char: int
    text: str
    text_sha256: str
    chunker_version: str
    max_chars: int
    overlap_chars: int
    created_at: datetime


class DocumentChunkBuildResponse(BaseModel):
    version: DocumentVersionResponse
    chunk_count: int
    chunked_page_count: int
    skipped_page_count: int
    max_chars: int
    overlap_chars: int
    chunker_version: str


class DocumentEmbeddingIndexBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    force_rebuild: bool = False


class DocumentEmbeddingIndexResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_version_id: uuid.UUID
    provider: str
    model_name: str
    model_revision: str
    dimensions: int
    state: str
    chunk_count: int
    created_at: datetime
    completed_at: datetime | None


class DocumentEmbeddingIndexBuildResponse(BaseModel):
    version: DocumentVersionResponse
    index: DocumentEmbeddingIndexResponse
