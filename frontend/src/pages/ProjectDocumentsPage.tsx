import {
  FormEvent,
  useCallback,
  useEffect,
  useState,
} from "react";
import {
  Link,
  Navigate,
  useParams,
} from "react-router-dom";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  documentsApi,
  sha256Hex,
  type DocumentClass,
  type DocumentSearchResponse,
  type PlanningDocumentResponse,
} from "../lib/api/documents";
import { ApiError } from "../lib/api/errors";
import {
  planningRunsApi,
  type PlanningRunResponse,
} from "../lib/api/planningRuns";
import { sitesApi } from "../lib/api/sites";
import { getSessionAccessToken } from "../lib/auth/session";

const classes: DocumentClass[] = [
  "RFN",
  "RSN",
  "RT",
  "RKK",
  "GPP",
  "CIRCULAR",
  "TECHNICAL_GUIDELINE",
  "LOCAL_AUTHORITY",
  "OTHER",
];

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown): UnknownRecord | undefined {
  if (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  ) {
    return value as UnknownRecord;
  }
  return undefined;
}

function stringValue(
  record: UnknownRecord | undefined,
  key: string,
): string | undefined {
  const value = record?.[key];
  return typeof value === "string" ? value : undefined;
}

function numberValue(
  record: UnknownRecord | undefined,
  key: string,
): number | undefined {
  const value = record?.[key];
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}

function cleanExcerpt(value: unknown): string {
  if (typeof value !== "string") {
    return "No text excerpt is available for this search result.";
  }
  return value.replace(/\s+/g, " ").trim();
}

function relevanceLabel(
  fusedScore: number | undefined,
  cosineSimilarity: number | undefined,
): string {
  const score = fusedScore ?? cosineSimilarity;
  if (score === undefined) return "Relevant";
  if (score >= 0.7) return "Very high";
  if (score >= 0.5) return "High";
  if (score >= 0.3) return "Moderate";
  return "Relevant";
}

function readableUnknown(value: unknown): string {
  if (typeof value === "string") return value;

  if (
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }

  const record = asRecord(value);
  if (record) {
    const preferred =
      stringValue(record, "summary") ??
      stringValue(record, "finding") ??
      stringValue(record, "text") ??
      stringValue(record, "message") ??
      stringValue(record, "description") ??
      stringValue(record, "conclusion");

    if (preferred) return preferred;
  }

  try {
    return JSON.stringify(value);
  } catch {
    return "Structured result";
  }
}


function displayProviderName(
  value: string | undefined,
): string {
  if (!value) {
    return "AI provider";
  }

  if (value.toLowerCase() === "openai") {
    return "OpenAI";
  }

  if (value.toLowerCase() === "ollama") {
    return "Ollama";
  }

  return value;
}

function providerMetadata(
  run: PlanningRunResponse,
): {
  provider?: string;
  model?: string;
} {
  const metadata = asRecord(
    run.provider_metadata,
  );

  return {
    provider: stringValue(
      metadata,
      "provider",
    ),
    model: stringValue(
      metadata,
      "model",
    ),
  };
}

export function ProjectDocumentsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const token = getSessionAccessToken();

  const [documents, setDocuments] = useState<
    PlanningDocumentResponse[]
  >([]);

  const [title, setTitle] = useState("");
  const [authority, setAuthority] =
    useState("PLANMalaysia");
  const [documentClass, setDocumentClass] =
    useState<DocumentClass>("RT");
  const [publicationYear, setPublicationYear] =
    useState<number>(new Date().getFullYear());
  const [file, setFile] = useState<File | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] =
    useState<DocumentSearchResponse>();

  const [aiQuestion, setAiQuestion] = useState("");
  const [aiRun, setAiRun] =
    useState<PlanningRunResponse>();

  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [status, setStatus] = useState<string>();
  const [error, setError] = useState<string>();
  const [aiError, setAiError] = useState<string>();

  const loadDocuments = useCallback(async () => {
    if (!projectId || !token) return;

    try {
      const result = await documentsApi.list(
        projectId,
        token,
      );
      setDocuments(result);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to load planning documents.",
      );
    }
  }, [projectId, token]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (!projectId) {
    return <Navigate to="/projects" replace />;
  }

  const activeProjectId = projectId;
  const activeToken = token;

  const aiProvider = aiRun
    ? providerMetadata(aiRun)
    : undefined;

  async function uploadDocument(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (!file) {
      setError("Choose a PDF file first.");
      return;
    }

    if (file.type !== "application/pdf") {
      setError(
        "Only PDF files are accepted for this workflow.",
      );
      return;
    }

    setBusy(true);
    setError(undefined);
    setStatus("Computing source checksum...");

    try {
      const checksum = await sha256Hex(file);

      setStatus(
        "Registering immutable planning document...",
      );

      const document = await documentsApi.create(
        activeProjectId,
        {
          title,
          document_class: documentClass,
          authority,
          jurisdiction: null,
          geographic_applicability: {},
          initial_version: {
            version_label: "v1",
            publication_year: publicationYear,
            source_kind: "upload",
            source_filename: file.name,
            mime_type:
              file.type || "application/pdf",
            file_size_bytes: file.size,
            checksum_sha256: checksum,
            provenance: {
              acquisition_method: "user_upload",
              original_filename: file.name,
            },
          },
        },
        activeToken,
      );

      const versions =
        await documentsApi.listVersions(
          activeProjectId,
          document.id,
          activeToken,
        );

      const version = versions[0];

      if (!version) {
        throw new Error(
          "Document version was not created.",
        );
      }

      setStatus(
        "Uploading and extracting PDF pages...",
      );

      const ingestion =
        await documentsApi.ingestPdf(
          activeProjectId,
          document.id,
          version.id,
          file,
          activeToken,
        );

      setStatus(
        `Extracted ${ingestion.text_page_count}/${ingestion.page_count} text pages. Building chunks...`,
      );

      const chunks =
        await documentsApi.buildChunks(
          activeProjectId,
          document.id,
          version.id,
          activeToken,
        );

      setStatus(
        `Built ${chunks.chunk_count} chunks. Building embedding index with configured provider...`,
      );

      await documentsApi.buildIndex(
        activeProjectId,
        document.id,
        version.id,
        activeToken,
      );

      setStatus(
        "Document ingestion and indexing complete.",
      );

      setTitle("");
      setFile(null);
      await loadDocuments();
    } catch (caught) {
      console.error(
        "DOCUMENT WORKFLOW ERROR:",
        caught,
      );

      setError(
        caught instanceof ApiError
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "Document workflow failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function searchDocuments(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const query = searchQuery.trim();
    if (!query) return;

    setBusy(true);
    setError(undefined);
    setSearchResult(undefined);

    try {
      const result = await documentsApi.search(
        activeProjectId,
        query,
        activeToken,
      );
      setSearchResult(result);
    } catch (caught) {
      console.error(
        "DOCUMENT SEARCH ERROR:",
        caught,
      );

      setError(
        caught instanceof ApiError
          ? caught.message
          : "Document search failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function askGeoPilot(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const question = aiQuestion.trim();
    if (!question) return;

    setAiBusy(true);
    setAiError(undefined);
    setAiRun(undefined);

    try {
      const activeSite = await sitesApi.active(
        activeProjectId,
        activeToken,
      );

      const created =
        await planningRunsApi.create(
          activeProjectId,
          activeSite.id,
          {
            question,
            development_intent: null,
          },
          activeToken,
        );

      const executed =
        await planningRunsApi.execute(
          activeProjectId,
          activeSite.id,
          created.id,
          activeToken,
        );

      setAiRun(executed);
    } catch (caught) {
      console.error(
        "GEOPILOT AI RUN ERROR:",
        caught,
      );

      setAiError(
        caught instanceof ApiError
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "GeoPilot AI analysis failed.",
      );
    } finally {
      setAiBusy(false);
    }
  }

  return (
    <section className="workspace-stack">
      <section className="panel">
        <p className="eyebrow">
          Planning Documents
        </p>

        <h1>
          Project document intelligence
        </h1>

        <p className="lede">
          Upload RFN, RSN, RT, RKK, GPP or other
          controlled planning sources. GeoPilot
          preserves checksum and version lineage
          before extraction, chunking and indexing.
        </p>

        <p>
          <Link
            to={`/projects/${activeProjectId}`}
          >
            Back to Project
          </Link>
        </p>
      </section>

      <section className="panel">
        <h2>Upload planning PDF</h2>

        <form
          className="stack-form"
          onSubmit={uploadDocument}
        >
          <label>
            Document title
            <input
              value={title}
              onChange={(event) =>
                setTitle(event.target.value)
              }
              required
              maxLength={300}
            />
          </label>

          <label>
            Document class
            <select
              value={documentClass}
              onChange={(event) =>
                setDocumentClass(
                  event.target
                    .value as DocumentClass,
                )
              }
            >
              {classes.map((value) => (
                <option
                  value={value}
                  key={value}
                >
                  {value}
                </option>
              ))}
            </select>
          </label>

          <label>
            Authority
            <input
              value={authority}
              onChange={(event) =>
                setAuthority(event.target.value)
              }
              required
            />
          </label>

          <label>
            Publication year
            <input
              type="number"
              min={1900}
              max={2200}
              value={publicationYear}
              onChange={(event) =>
                setPublicationYear(
                  Number(event.target.value),
                )
              }
            />
          </label>

          <label>
            PDF file
            <input
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) =>
                setFile(
                  event.target.files?.[0] ??
                    null,
                )
              }
              required
            />
          </label>

          <button
            type="submit"
            disabled={busy}
          >
            {busy
              ? "Processing..."
              : "Upload, Extract & Index"}
          </button>
        </form>

        {status && (
          <div className="status-card">
            {status}
          </div>
        )}

        {error && (
          <div
            className="status-card status-error"
            role="alert"
          >
            {error}
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Project documents</h2>

        {documents.length === 0 ? (
          <p>
            No planning documents registered yet.
          </p>
        ) : (
          <div className="card-list">
            {documents.map((document) => (
              <article
                className="resource-card"
                key={document.id}
              >
                <div>
                  <strong>
                    {document.title}
                  </strong>
                  <p>
                    {document.document_class}
                    {" | "}
                    {document.authority}
                  </p>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <p className="eyebrow">
          GeoPilot AI
        </p>

        <h2>Ask GeoPilot AI</h2>

        <p>
          GeoPilot runs the question against the
          active Site and the project evidence
          available to the Planning Officer.
        </p>

        <form
          className="stack-form"
          onSubmit={askGeoPilot}
        >
          <label>
            Planning question
            <textarea
              value={aiQuestion}
              onChange={(event) =>
                setAiQuestion(
                  event.target.value,
                )
              }
              placeholder="Example: What density values are mentioned in the planning evidence and what do they mean for this site?"
              required
              minLength={3}
            />
          </label>

          <button
            type="submit"
            disabled={
              aiBusy ||
              !aiQuestion.trim()
            }
          >
            {aiBusy
              ? "GeoPilot is analysing..."
              : "Analyse with GeoPilot AI"}
          </button>
        </form>

        {aiError && (
          <div
            className="status-card status-error"
            role="alert"
          >
            {aiError}
          </div>
        )}

        {aiRun && (
          <div className="search-results">
            <div className="status-card">
              <strong>
                AI analysis
              </strong>
              <p>
                Status:{" "}
                <strong>{aiRun.status}</strong>
                {" | "}
                Review:{" "}
                <strong>{aiRun.review_state}</strong>

                {aiProvider?.provider && (
                  <>
                    {" | "}
                    Provider:{" "}
                    <strong>
                      {displayProviderName(
                        aiProvider.provider,
                      )}
                    </strong>
                  </>
                )}

                {aiProvider?.model && (
                  <>
                    {" | "}
                    Model:{" "}
                    <strong>
                      {aiProvider.model}
                    </strong>
                  </>
                )}
              </p>
            </div>

            <article className="resource-card">
              <div>
                <p className="eyebrow">
                  GeoPilot synthesis
                </p>
                <h3>Answer</h3>
                {aiRun.synthesis ? (
                  <div className="geopilot-markdown">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {aiRun.synthesis}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <p>
                    The Planning Run completed without a
                    synthesis response.
                  </p>
                )}
              </div>
            </article>

            {aiRun.findings.length > 0 && (
              <div className="status-card">
                <strong>
                  Key findings
                </strong>
                <ul>
                  {aiRun.findings.map(
                    (finding, index) => (
                      <li key={index}>
                        {readableUnknown(
                          finding,
                        )}
                      </li>
                    ),
                  )}
                </ul>
              </div>
            )}

            <div className="status-card">
              <strong>
                Evidence traceability
              </strong>
              <p>
                {aiRun.evidence.length} evidence item
                {aiRun.evidence.length === 1
                  ? ""
                  : "s"}{" "}
                retained in this Planning Run.
              </p>
            </div>

            {aiRun.limitations.length > 0 && (
              <div className="status-card">
                <strong>
                  Limitations
                </strong>
                <ul>
                  {aiRun.limitations.map(
                    (limitation, index) => (
                      <li key={index}>
                        {readableUnknown(
                          limitation,
                        )}
                      </li>
                    ),
                  )}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="panel">
        <h2>
          Search planning evidence
        </h2>

        <p>
          Search the indexed planning documents for
          relevant source passages. Results below
          are evidence retrieval results, not a
          statutory planning determination.
        </p>

        <form
          className="stack-form"
          onSubmit={searchDocuments}
        >
          <label>
            Question / search query
            <textarea
              value={searchQuery}
              onChange={(event) =>
                setSearchQuery(
                  event.target.value,
                )
              }
              placeholder="Example: What density values are mentioned in the document?"
              required
              minLength={2}
            />
          </label>

          <button
            type="submit"
            disabled={
              busy ||
              !searchQuery.trim()
            }
          >
            {busy
              ? "Searching..."
              : "Search evidence"}
          </button>
        </form>

        {searchResult && (
          <div className="search-results">
            <div className="status-card">
              <strong>
                Search summary
              </strong>

              <p>
                {searchResult.result_count}{" "}
                relevant passage
                {searchResult.result_count === 1
                  ? ""
                  : "s"}{" "}
                found.
              </p>

              <p>
                Status:{" "}
                <strong>
                  {searchResult.status}
                </strong>
                {" | "}
                Mode:{" "}
                <strong>
                  {searchResult.search_mode}
                </strong>
              </p>
            </div>

            {searchResult.limitations.length >
              0 && (
              <div className="status-card">
                <strong>
                  Search limitations
                </strong>
                <ul>
                  {searchResult.limitations.map(
                    (limitation) => (
                      <li key={limitation}>
                        {limitation}
                      </li>
                    ),
                  )}
                </ul>
              </div>
            )}

            {searchResult.hits.length ===
            0 ? (
              <div className="status-card">
                No relevant indexed evidence was
                found for this query.
              </div>
            ) : (
              <div className="card-list">
                {searchResult.hits.map(
                  (hit, index) => {
                    const hitRecord =
                      asRecord(hit);

                    const provenance =
                      asRecord(
                        hitRecord?.provenance,
                      );

                    const rank =
                      numberValue(
                        hitRecord,
                        "rank",
                      ) ??
                      index + 1;

                    const pageNumber =
                      numberValue(
                        provenance,
                        "page_number",
                      );

                    const documentTitle =
                      stringValue(
                        provenance,
                        "document_title",
                      ) ??
                      "Planning document";

                    const resultDocumentClass =
                      stringValue(
                        provenance,
                        "document_class",
                      );

                    const hitAuthority =
                      stringValue(
                        provenance,
                        "authority",
                      );

                    const resultPublicationYear =
                      numberValue(
                        provenance,
                        "publication_year",
                      );

                    const versionLabel =
                      stringValue(
                        provenance,
                        "version_label",
                      );

                    const chunkId =
                      stringValue(
                        provenance,
                        "document_chunk_id",
                      ) ??
                      stringValue(
                        provenance,
                        "chunk_id",
                      );

                    const text =
                      cleanExcerpt(
                        hitRecord?.text,
                      );

                    const fusedScore =
                      numberValue(
                        hitRecord,
                        "fused_score",
                      );

                    const cosineSimilarity =
                      numberValue(
                        hitRecord,
                        "cosine_similarity",
                      );

                    const relevance =
                      relevanceLabel(
                        fusedScore,
                        cosineSimilarity,
                      );

                    return (
                      <article
                        className="resource-card"
                        key={
                          chunkId ??
                          `${rank}-${index}`
                        }
                      >
                        <div>
                          <p className="eyebrow">
                            Result {rank}
                          </p>

                          <h3>
                            {documentTitle}
                          </h3>

                          <p>
                            {pageNumber !==
                              undefined &&
                              `Page ${pageNumber}`}

                            {resultDocumentClass &&
                              ` | ${resultDocumentClass}`}

                            {hitAuthority &&
                              ` | ${hitAuthority}`}

                            {resultPublicationYear !==
                              undefined &&
                              ` | ${resultPublicationYear}`}

                            {versionLabel &&
                              ` | ${versionLabel}`}
                          </p>

                          <p>
                            <strong>
                              Relevance:
                            </strong>{" "}
                            {relevance}
                          </p>

                          <p>{text}</p>
                        </div>
                      </article>
                    );
                  },
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </section>
  );
}