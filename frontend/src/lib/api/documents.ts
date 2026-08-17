import { apiClient } from "./client";

export type DocumentClass =
  | "RFN"
  | "RSN"
  | "RT"
  | "RKK"
  | "GPP"
  | "CIRCULAR"
  | "TECHNICAL_GUIDELINE"
  | "LOCAL_AUTHORITY"
  | "OTHER";

export type PlanningDocumentResponse = {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  document_class: string;
  authority: string;
  jurisdiction: string | null;
  geographic_applicability: Record<string, unknown>;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
};

export type DocumentVersionResponse = {
  id: string;
  document_id: string;
  version_sequence: number;
  version_label: string | null;
  publication_year: number | null;
  publication_date: string | null;
  source_kind: string;
  source_filename: string | null;
  source_uri: string | null;
  storage_uri: string | null;
  mime_type: string;
  file_size_bytes: number | null;
  checksum_sha256: string;
  ingestion_state: string;
  extraction_state: string;
  index_state: string;
  review_state: string;
  provenance: Record<string, unknown>;
  created_at: string;
};

export type PdfIngestionResponse = {
  version: DocumentVersionResponse;
  page_count: number;
  text_page_count: number;
  requires_ocr_page_count: number;
  extraction_state: string;
  review_state: string;
};

export type DocumentChunkBuildResponse = {
  version: DocumentVersionResponse;
  chunk_count: number;
  chunked_page_count: number;
  skipped_page_count: number;
  max_chars: number;
  overlap_chars: number;
  chunker_version: string;
};

export type DocumentEmbeddingIndexBuildResponse = {
  version: DocumentVersionResponse;
  index: Record<string, unknown>;
};

export type DocumentSearchHit = Record<string, unknown>;

export type DocumentSearchResponse = {
  status: "evaluated" | "insufficient_evidence" | "degraded";
  search_mode: "hybrid" | "keyword_only";
  query: string;
  result_count: number;
  hits: DocumentSearchHit[];
  limitations: string[];
};

function bearer(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export async function sha256Hex(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export const documentsApi = {
  list: (projectId: string, accessToken: string) =>
    apiClient.get<PlanningDocumentResponse[]>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/documents`,
      { headers: bearer(accessToken) },
    ),

  create: (
    projectId: string,
    payload: {
      title: string;
      description?: string | null;
      document_class: DocumentClass;
      authority: string;
      jurisdiction?: string | null;
      geographic_applicability?: Record<string, unknown>;
      initial_version: {
        version_label?: string | null;
        publication_year?: number | null;
        source_kind: "upload";
        source_filename: string;
        mime_type: string;
        file_size_bytes: number;
        checksum_sha256: string;
        provenance: Record<string, unknown>;
      };
    },
    accessToken: string,
  ) =>
    apiClient.request<PlanningDocumentResponse>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/documents`,
      {
        method: "POST",
        headers: {
          ...bearer(accessToken),
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),

  listVersions: (
    projectId: string,
    documentId: string,
    accessToken: string,
  ) =>
    apiClient.get<DocumentVersionResponse[]>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/versions`,
      { headers: bearer(accessToken) },
    ),

  ingestPdf: (
    projectId: string,
    documentId: string,
    versionId: string,
    file: File,
    accessToken: string,
  ) => {
    const formData = new FormData();
    formData.append("file", file);

    return apiClient.request<PdfIngestionResponse>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/ingest-pdf`,
      {
        method: "POST",
        headers: bearer(accessToken),
        body: formData,
      },
    );
  },

  buildChunks: (
    projectId: string,
    documentId: string,
    versionId: string,
    accessToken: string,
  ) =>
    apiClient.request<DocumentChunkBuildResponse>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/chunks/build`,
      {
        method: "POST",
        headers: {
          ...bearer(accessToken),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          max_chars: 1200,
          overlap_chars: 200,
        }),
      },
    ),

  buildIndex: (
    projectId: string,
    documentId: string,
    versionId: string,
    accessToken: string,
  ) =>
    apiClient.request<DocumentEmbeddingIndexBuildResponse>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/chunks/index`,
      {
        method: "POST",
        headers: {
          ...bearer(accessToken),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          force_rebuild: false,
        }),
      },
    ),

  search: (
    projectId: string,
    query: string,
    accessToken: string,
  ) =>
    apiClient.request<DocumentSearchResponse>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/document-search`,
      {
        method: "POST",
        headers: {
          ...bearer(accessToken),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query,
          top_k: 10,
          candidate_limit: 50,
        }),
      },
    ),
};