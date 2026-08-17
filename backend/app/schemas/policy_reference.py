from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.schemas.citations import DocumentCitationReference, ResolvedDocumentCitation

ApplicabilityStatus = Literal["unassessed", "requires_review", "applicable", "not_applicable", "limited"]
ReviewAction = Literal["verify", "reject", "requires_review"]


class PolicyReferenceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation: DocumentCitationReference
    label: str | None = Field(default=None, max_length=255)
    policy_statement: str = Field(min_length=1, max_length=6000)
    applicability_notes: str | None = Field(default=None, max_length=6000)


class PolicyReferenceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=255)
    policy_statement: str | None = Field(default=None, min_length=1, max_length=6000)
    applicability_notes: str | None = Field(default=None, max_length=6000)
    is_archived: bool | None = None


class PolicyReferenceReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ReviewAction
    applicability_status: ApplicabilityStatus = "unassessed"
    applicability_notes: str | None = Field(default=None, max_length=6000)
    review_notes: str | None = Field(default=None, max_length=6000)

    @model_validator(mode="after")
    def validate_action(self):
        if self.action == "requires_review" and self.applicability_status not in {"unassessed", "requires_review"}:
            raise ValueError("requires_review action may not assert a final applicability status")
        return self


class PolicyReferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    project_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    document_page_id: uuid.UUID
    document_chunk_id: uuid.UUID
    created_by_user_id: uuid.UUID
    reviewed_by_user_id: uuid.UUID | None
    label: str | None
    document_class_snapshot: str
    authority_snapshot: str
    page_number: int
    version_checksum_sha256: str
    page_text_sha256: str
    chunk_text_sha256: str
    source_wording: str
    policy_statement: str
    representation_state: str
    review_state: str
    applicability_status: str
    applicability_notes: str | None
    review_notes: str | None
    is_archived: bool
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def source_citation(self) -> DocumentCitationReference:
        return DocumentCitationReference(
            project_id=self.project_id,
            document_id=self.document_id,
            document_version_id=self.document_version_id,
            document_page_id=self.document_page_id,
            document_chunk_id=self.document_chunk_id,
            page_number=self.page_number,
            version_checksum_sha256=self.version_checksum_sha256,
            page_text_sha256=self.page_text_sha256,
            chunk_text_sha256=self.chunk_text_sha256,
        )


class PolicyReferenceUseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["validated"] = "validated"
    policy_reference: PolicyReferenceResponse
    source_citation: ResolvedDocumentCitation
    limitations: list[str]
