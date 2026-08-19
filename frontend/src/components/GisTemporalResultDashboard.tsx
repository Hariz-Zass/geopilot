import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ProjectTemporalAskResponse, TrackBGisTemporalResult } from "../lib/api/trackB";

type Props = {
  result: TrackBGisTemporalResult;
  onAsk: (question: string) => Promise<ProjectTemporalAskResponse>;
  view?: "gis" | "ask" | "evidence";
  onAskTab?: () => void;
};

function number(value: number) {
  return value.toLocaleString("en-US");
}

const TEMPORAL_QUESTIONS = [
  "What are the biggest verified land-use transitions?",
  "How much verified area was reclassified?",
  "What did Tanah Kosong change into?",
];

type ResponseSection = { title: string; body: string };

function responseSections(markdown: string): ResponseSection[] {
  const sections: ResponseSection[] = [];
  const matches = [...markdown.matchAll(/^#{2,4}\s+(.+)$/gm)];
  const first = matches[0];
  if (!first) return [{ title: "Key Finding", body: markdown }];
  if (first.index && markdown.slice(0, first.index).trim()) {
    sections.push({ title: "Key Finding", body: markdown.slice(0, first.index).trim() });
  }
  matches.forEach((match, index) => {
    const start = (match.index ?? 0) + match[0].length;
    const end = matches[index + 1]?.index ?? markdown.length;
    const title = (match[1] ?? "Section").replace(/[*_`]/g, "").trim();
    sections.push({ title, body: markdown.slice(start, end).trim() });
  });
  return sections.filter((section) => section.body);
}

function MarkdownBlock({ value }: { value: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>;
}

export function GisTemporalResultDashboard({ result, onAsk, view = "gis", onAskTab }: Props) {
  const [question, setQuestion] = useState("What are the biggest verified land-use transitions?");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<ProjectTemporalAskResponse>();

  async function ask() {
    if (!question.trim()) return;
    setAsking(true);
    try {
      setAnswer(await onAsk(question));
    } finally {
      setAsking(false);
    }
  }

  const showEvidence = view === "evidence";
  const showAsk = view === "ask";

  return (
    <section className={`gis-temporal-result-dashboard gis-dashboard-view-${view}`} aria-live="polite">
      <div className="gis-result-heading">
        <div>
          <span className="decision-kicker">GIS VECTOR TEMPORAL CHANGE</span>
          <h2>GIS TEMPORAL CHANGE INTELLIGENCE</h2>
          <p>Verified exact-geometry evidence for the selected land-use dataset pair.</p>
        </div>
        <div className="gis-result-status"><strong>{result.confidence}</strong><span>{result.matching_method} · DETERMINISTIC</span></div>
      </div>

      <div className="gis-result-grounding" aria-label="GIS temporal grounding">
        <span>GROUNDING</span><strong>{result.dataset_pair.before_year} → {result.dataset_pair.after_year}</strong><b>{result.matching_method} · {result.confidence}</b>
      </div>

      {showEvidence ? <details className="gis-result-provenance gis-result-provenance-expanded" open>
        <summary>Evidence Lineage · provenance and audit metadata</summary>
        <div><span>Analysis ID</span><code>{result.analysis_id}</code></div>
        <div><span>Project ID</span><code>{result.project_id ?? "Not supplied"}</code></div>
        <div><span>Before checksum</span><code>{result.checksums.before}</code></div>
        <div><span>After checksum</span><code>{result.checksums.after}</code></div>
        <div><span>Before year</span><code>{result.dataset_pair.before_year}</code></div>
        <div><span>After year</span><code>{result.dataset_pair.after_year}</code></div>
        <div><span>Method</span><code>{result.matching_method}</code></div>
        <div><span>Deterministic</span><code>{String(result.deterministic)}</code></div>
        <div><span>Source identity</span><code>{String(result.source_provenance.id ?? `analysis:${result.analysis_id}`)}</code></div>
      </details> : <>
      {showAsk && <div className="gis-ask-grounding"><span>GROUNDING:</span><strong>{result.dataset_pair.before_dataset} → {result.dataset_pair.after_dataset}</strong><b>{result.matching_method} · {result.confidence}</b></div>}
      <div className="gis-result-pair" aria-label="GIS temporal dataset pair">
        <div><small>BEFORE</small><strong>{result.dataset_pair.before_dataset}</strong><span>{result.dataset_pair.before_year}</span></div>
        <b aria-hidden="true">→</b>
        <div><small>AFTER</small><strong>{result.dataset_pair.after_dataset}</strong><span>{result.dataset_pair.after_year}</span></div>
      </div>

      {!showAsk && <div className="gis-result-metrics">
        <article><small>EXACT GEOMETRY MATCHES</small><strong>{number(result.exact_match_count)}</strong><span>Matched polygons</span></article>
        <article><small>UNCHANGED EXACT MATCHES</small><strong>{number(result.unchanged_count)}</strong><span>Unchanged attributes</span></article>
        <article><small>VERIFIED LAND-USE RECLASSIFICATIONS</small><strong>{number(result.verified_reclassified_count)}</strong><span>polygons · exact-geometry reclassification</span></article>
        <article><small>VERIFIED RECLASSIFIED AREA</small><strong>{result.verified_changed_area_ha.toFixed(3)} <em>ha</em></strong><span>Among exact-geometry matches</span></article>
      </div>}

      {!showAsk && <section className="gis-result-transitions">
        <div className="gis-result-section-title"><span>BOUNDED EVIDENCE</span><h3>TOP VERIFIED TRANSITIONS</h3></div>
        {result.top_gtn1_transitions.length ? result.top_gtn1_transitions.map((transition, index) => (
          <article key={`${transition.before_category}-${transition.after_category}-${index}`}>
            <strong>{transition.before_category || "Unclassified"} <span>→</span> {transition.after_category || "Unclassified"}</strong>
            <small>{number(transition.feature_count)} polygons · {transition.measured_area_ha.toFixed(3)} ha</small>
          </article>
        )) : <p className="gis-result-muted">No bounded GTN1 transitions were returned.</p>}
      </section>}

      {!showAsk && <details className="gis-result-limitations">
        <summary><span>METHOD & LIMITATIONS</span><strong>Exact-only evidence boundary</strong></summary>
        <div className="gis-result-limitations-body">
        <p>Method: <strong>{result.matching_method}</strong> · status: <strong>{result.confidence}</strong> · deterministic.</p>
        <ul>
          {result.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
        </ul>
        </div>
      </details>}

      {!showAsk && <details className="gis-result-provenance">
        <summary>Evidence Lineage · provenance and audit metadata</summary>
        <div><span>Analysis ID</span><code>{result.analysis_id}</code></div>
        <div><span>Project ID</span><code>{result.project_id ?? "Not supplied"}</code></div>
        <div><span>Before checksum</span><code>{result.checksums.before}</code></div>
        <div><span>After checksum</span><code>{result.checksums.after}</code></div>
        <div><span>Source identity</span><code>{String(result.source_provenance.id ?? `analysis:${result.analysis_id}`)}</code></div>
      </details>}
      </>}

      {(showAsk || !showEvidence) && <section className="gis-result-ask">
        <div><span className="decision-kicker">GEOPILOT PLANNING COPILOT</span><h3>Measured GIS evidence is available</h3><p>Ask GeoPilot about this exact-geometry result through the existing grounded evidence handoff.</p></div>
        <div className="gis-result-ask-controls">
          <div className="gis-result-question-shortcuts" aria-label="Suggested GIS questions">
            {TEMPORAL_QUESTIONS.map((suggestion) => <button key={suggestion} type="button" className={question === suggestion ? "active" : ""} onClick={() => setQuestion(suggestion)}>{suggestion}</button>)}
          </div>
          <label className="gis-result-question-label">Ask a question
            <textarea aria-label="Free-text GIS question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about verified change, transitions, or area." rows={3} />
          </label>
          <button className="analysis-button" type="button" disabled={asking || !question.trim()} onClick={() => { onAskTab?.(); void ask(); }}>{asking ? "Preparing GeoPilot…" : "Ask GeoPilot about this result"}</button>
        </div>
        {answer && <details className="gis-result-answer" open>
          <summary>GeoPilot response · {answer.status}</summary>
          <div className="gis-answer-sections">
            {responseSections(answer.synthesis || "Validated evidence was handed off, but no synthesis was produced.").map((section) => <section key={section.title}><h4>{section.title}</h4><div className="gis-answer-markdown"><MarkdownBlock value={section.body} /></div></section>)}
            {!!answer.evidence.length && <section><h4>Supporting Evidence</h4><div className="gis-answer-evidence">{answer.evidence.slice(0, 5).map((item, index) => <div key={index}><strong>{String(item.label ?? item.category ?? item.name ?? `Evidence ${index + 1}`)}</strong><span>{Object.entries(item).filter(([key]) => key !== "label" && key !== "category" && key !== "name").slice(0, 3).map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}</span></div>)}</div></section>}
          </div>
          <details className="gis-answer-boundary"><summary>Evidence Boundary</summary><ul>{answer.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></details>
        </details>}
      </section>}
    </section>
  );
}
