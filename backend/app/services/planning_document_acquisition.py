from __future__ import annotations

import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import httpx


MAX_DOCUMENT_BYTES = 100 * 1024 * 1024
MAX_REDIRECTS = 5
OFFICIAL_HOST_SUFFIXES = (
    "planmalaysia.gov.my",
    "myplan.planmalaysia.gov.my",
)


class PlanningDocumentAcquisitionError(Exception):
    pass


@dataclass(frozen=True)
class PlanningDocumentCandidate:
    document_class: str
    title: str
    authority: str
    jurisdiction: str | None
    source_uri: str
    provider: str
    metadata: dict


@dataclass(frozen=True)
class AcquiredPlanningDocument:
    candidate: PlanningDocumentCandidate
    content: bytes
    mime_type: str
    checksum_sha256: str
    final_uri: str


class PlanningDocumentProvider(Protocol):
    name: str

    def discover(
        self,
        *,
        document_class: str,
        jurisdiction: str | None,
        query: str,
    ) -> list[PlanningDocumentCandidate]:
        ...


def _official_host(host: str | None) -> bool:
    if not host:
        return False
    host = host.rstrip(".").casefold()
    return any(
        host == suffix or host.endswith("." + suffix)
        for suffix in OFFICIAL_HOST_SUFFIXES
    )


def _public_dns_only(host: str) -> None:
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                host,
                443,
                type=socket.SOCK_STREAM,
            )
        }
    except OSError as exc:
        raise PlanningDocumentAcquisitionError(
            "Official document host could not be resolved."
        ) from exc

    if not addresses:
        raise PlanningDocumentAcquisitionError(
            "Official document host resolved to no addresses."
        )

    for value in addresses:
        ip = ipaddress.ip_address(value)
        if not ip.is_global:
            raise PlanningDocumentAcquisitionError(
                "Document acquisition rejected a non-public network target."
            )


def validate_official_source_uri(uri: str) -> str:
    parsed = urlparse(uri)

    if parsed.scheme.casefold() != "https":
        raise PlanningDocumentAcquisitionError(
            "Planning document acquisition requires HTTPS."
        )

    if parsed.username or parsed.password:
        raise PlanningDocumentAcquisitionError(
            "Planning document source URI must not contain credentials."
        )

    if parsed.port not in (None, 443):
        raise PlanningDocumentAcquisitionError(
            "Planning document source URI must use standard HTTPS."
        )

    if not _official_host(parsed.hostname):
        raise PlanningDocumentAcquisitionError(
            "Planning document source is not an approved official PLANMalaysia host."
        )

    _public_dns_only(parsed.hostname or "")
    return uri


def acquire_candidate(
    candidate: PlanningDocumentCandidate,
    *,
    client: httpx.Client | None = None,
    max_bytes: int = MAX_DOCUMENT_BYTES,
) -> AcquiredPlanningDocument:
    current = validate_official_source_uri(candidate.source_uri)

    own_client = client is None
    http = client or httpx.Client(
        timeout=httpx.Timeout(60.0),
        follow_redirects=False,
    )

    try:
        for _ in range(MAX_REDIRECTS + 1):
            response = http.get(
                current,
                headers={
                    "Accept": "application/pdf,application/octet-stream;q=0.9"
                },
            )

            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise PlanningDocumentAcquisitionError(
                        "Official source returned a redirect without Location."
                    )

                current = validate_official_source_uri(
                    urljoin(current, location)
                )
                continue

            response.raise_for_status()

            content = response.content
            if not content:
                raise PlanningDocumentAcquisitionError(
                    "Official document response was empty."
                )

            if len(content) > max_bytes:
                raise PlanningDocumentAcquisitionError(
                    "Official document exceeded the configured safety limit."
                )

            if not content.startswith(b"%PDF-"):
                raise PlanningDocumentAcquisitionError(
                    "Official document response was not a valid PDF payload."
                )

            return AcquiredPlanningDocument(
                candidate=candidate,
                content=content,
                mime_type="application/pdf",
                checksum_sha256=hashlib.sha256(content).hexdigest(),
                final_uri=current,
            )

        raise PlanningDocumentAcquisitionError(
            "Official document exceeded the redirect limit."
        )

    except httpx.HTTPError as exc:
        raise PlanningDocumentAcquisitionError(
            "Official planning document could not be downloaded."
        ) from exc

    finally:
        if own_client:
            http.close()



class _CatalogueLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.links=[]; self.href=None; self.text=[]
    def handle_starttag(self, tag, attrs):
        if tag.casefold()=="a": self.href=dict(attrs).get("href"); self.text=[]
    def handle_data(self, data):
        if self.href is not None: self.text.append(data)
    def handle_endtag(self, tag):
        if tag.casefold()=="a" and self.href is not None:
            self.links.append((" ".join("".join(self.text).split()),self.href)); self.href=None; self.text=[]

def _normalized_uri(uri):
    x=urlparse(uri); return urlunparse((x.scheme.casefold(),x.netloc.casefold(),x.path,"",x.query,""))

def _with_page(uri,page):
    x=urlparse(uri); q=parse_qs(x.query,keep_blank_values=True); q["page"]=[str(page)]
    return urlunparse(x._replace(query=urlencode(q,doseq=True)))


_CATALOGUE_STOPWORDS = {
    "apa", "apakah", "adakah", "bagaimana", "berapa", "nyatakan", "senaraikan",
    "jelaskan", "terangkan", "berikan", "bagi", "sertakan", "tunjukkan",
    "sumber", "bukti", "rujukan", "rasmi", "planmalaysia", "dokumen",
    "yang", "dan", "atau", "dalam", "daripada", "dari", "kepada", "untuk",
    "pada", "di", "ke", "ini", "itu", "tersebut", "adalah", "ialah",
    "berdasarkan", "menurut", "terdapat", "dinyatakan", "berkaitan",
    "mengenai", "tentang", "jangan", "reka", "maklumat",
    "please", "what", "which", "how", "state", "list", "show", "give",
    "provide", "include", "source", "evidence", "official", "document",
    "based", "according", "mentioned", "stated", "the", "a", "an",
    "of", "in", "on", "for", "to", "and", "or",
}

_CATALOGUE_CLASS_TERMS = {
    "gpp", "rfn", "rsn", "rt", "rkk", "garis", "panduan", "perancangan",
    "rancangan", "tempatan", "struktur", "negeri", "kawasan", "khas",
}

def _catalogue_terms(query: str) -> list[str]:
    raw = " ".join((query or "").casefold().split())
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "/"} else " " for ch in raw)
    out, seen = [], set()
    for token in normalized.split():
        token = token.strip("-/")
        if not token or len(token) <= 1 or token in _CATALOGUE_STOPWORDS:
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out

def _catalogue_candidate_score(title: str, query: str) -> tuple[int, int, int]:
    title_low = " ".join((title or "").casefold().split())
    terms = _catalogue_terms(query)
    if not terms:
        return (0, 0, 0)
    meaningful = [t for t in terms if t not in _CATALOGUE_CLASS_TERMS]
    basis = meaningful or terms
    matched = [t for t in basis if t in title_low]
    class_matched = [t for t in terms if t in _CATALOGUE_CLASS_TERMS and t in title_low]
    phrase = " ".join(basis)
    return (len(matched), int(bool(phrase and phrase in title_low)), len(class_matched))

def _rank_catalogue_candidates(items, query: str):
    terms = _catalogue_terms(query)
    if not terms:
        return list(items)
    meaningful = [t for t in terms if t not in _CATALOGUE_CLASS_TERMS]
    basis = meaningful or terms
    minimum = 1 if len(basis) <= 1 else 2
    scored = []
    for item in items:
        score = _catalogue_candidate_score(item.title, query)
        if score[0] < minimum:
            continue
        scored.append((score, item.title.casefold(), item))
    scored.sort(key=lambda x: (x[0][0], x[0][1], x[0][2]), reverse=True)
    return [item for _, _, item in scored]
_EPUBLISITI_QUERY_NOISE = {
    "dasar", "cadangan", "pembangunan", "guna", "tanah", "syarat",
    "parameter", "polisi", "strategi", "hala", "tuju", "laporan",
    "kandungan", "maklumat", "perkara", "nilai", "ketetapan", "keperluan",
    "densiti", "intensiti", "zon", "zoning", "kelas", "kategori",
    "daerah", "majlis", "perbandaran", "bandar", "sebahagian",
}

_EPUBLISITI_WRAPPER_SIGNALS = (
    "notis publisiti",
    "program publisiti",
    "pemberitahuan",
    "penyertaan awam",
    "laporan tinjauan",
)

def _jurisdiction_terms(jurisdiction: str | None) -> list[str]:
    if not jurisdiction:
        return []
    return [
        token
        for token in _catalogue_terms(jurisdiction)
        if token not in _CATALOGUE_CLASS_TERMS
    ]

def _epublisiti_identity_phrase(document_class: str) -> str:
    return {
        "RT": "rancangan tempatan",
        "RSN": "rancangan struktur negeri",
        "RKK": "rancangan kawasan khas",
    }.get(document_class.upper(), "")

def _epublisiti_discriminators(
    query: str,
    *,
    jurisdiction: str | None,
) -> list[str]:
    jurisdiction_terms = set(_jurisdiction_terms(jurisdiction))
    out = []
    for token in _catalogue_terms(query):
        if token in _CATALOGUE_CLASS_TERMS:
            continue
        if token in _EPUBLISITI_QUERY_NOISE:
            continue
        if token in jurisdiction_terms:
            continue
        if token.isdigit():
            continue
        out.append(token)
    return out

def _rank_epublisiti_candidates(
    items,
    query: str,
    *,
    document_class: str,
    jurisdiction: str | None,
):
    identity_phrase = _epublisiti_identity_phrase(document_class)
    jurisdiction_terms = _jurisdiction_terms(jurisdiction)
    discriminators = _epublisiti_discriminators(
        query,
        jurisdiction=jurisdiction,
    )
    query_years = [
        token for token in _catalogue_terms(query)
        if token.isdigit()
    ]

    ranked = []
    for item in items:
        title_low = " ".join((item.title or "").casefold().split())

        if identity_phrase and identity_phrase not in title_low:
            continue

        discriminator_matches = [
            token for token in discriminators
            if token in title_low
        ]

        if discriminators:
            # A specific locality/topic phrase was supplied. All strong
            # discriminator tokens must match so "Perak Tengah" cannot also
            # accept "Hulu Perak" merely because both share Perak/2030.
            if len(discriminator_matches) != len(discriminators):
                continue
        elif jurisdiction_terms:
            # With no specific locality/topic discriminator, fail closed unless
            # the candidate title itself explicitly proves the requested state.
            if not all(token in title_low for token in jurisdiction_terms):
                continue

        base_score = _catalogue_candidate_score(item.title, query)
        year_matches = sum(1 for year in query_years if year in title_low)
        jurisdiction_matches = sum(
            1 for token in jurisdiction_terms if token in title_low
        )
        directness = -sum(
            1 for signal in _EPUBLISITI_WRAPPER_SIGNALS
            if signal in title_low
        )

        score = (
            len(discriminator_matches),
            jurisdiction_matches,
            year_matches,
            base_score[0],
            base_score[2],
            directness,
        )
        ranked.append((score, item.title.casefold(), item))

    ranked.sort(
        key=lambda x: (
            x[0][0], x[0][1], x[0][2],
            x[0][3], x[0][4], x[0][5],
        ),
        reverse=True,
    )
    return [item for _, _, item in ranked]




class _DocumentLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._row_depth = 0
        self._row_text = []
        self._row_links = []
        self._anchor_href = None
        self._anchor_text = []

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        attrs = dict(attrs)
        if tag == "tr":
            self._row_depth += 1
            if self._row_depth == 1:
                self._row_text = []
                self._row_links = []
        if tag == "a":
            self._anchor_href = attrs.get("href")
            self._anchor_text = []

    def handle_data(self, data):
        if self._row_depth:
            self._row_text.append(data)
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if tag == "a" and self._anchor_href is not None:
            item = {
                "href": self._anchor_href,
                "anchor_text": " ".join("".join(self._anchor_text).split()),
                "context": "",
            }
            if self._row_depth:
                self._row_links.append(item)
            else:
                self.links.append(item)
            self._anchor_href = None
            self._anchor_text = []
        elif tag == "tr" and self._row_depth:
            if self._row_depth == 1:
                context = " ".join("".join(self._row_text).split())
                for item in self._row_links:
                    item["context"] = context
                    self.links.append(item)
                self._row_text = []
                self._row_links = []
            self._row_depth -= 1


def _clean_resolved_title(context, anchor_text, fallback):
    value = " ".join((context or "").split())
    for token in ("Muat-Turun", "Muat Turun", "Download"):
        value = value.replace(token, " ")
    value = " ".join(value.split())
    if not value:
        value = " ".join((anchor_text or "").split())
    if not value or value.casefold() in {"muat-turun", "muat turun", "download"}:
        value = fallback
    return value[:500]

class PlanMalaysiaOfficialProvider:
    name = "planmalaysia_official"
    GPP_CATALOGUE_URL = "https://www.planmalaysia.gov.my/main/document-list?type=garis-panduan-perancangan"
    EPUBLISITI_HOME_URL = "https://www.planmalaysia.gov.my/epublisiti/home"
    MAX_GPP_PAGES = 20

    STATE_SLUGS = {
        "johor": "johor", "kedah": "kedah", "kelantan": "kelantan",
        "melaka": "melaka", "negeri sembilan": "negeri-sembilan",
        "pahang": "pahang", "perak": "perak", "perlis": "perlis",
        "pulau pinang": "pulau-pinang", "selangor": "selangor",
        "terengganu": "terengganu", "labuan": "labuan",
        "wilayah persekutuan labuan": "labuan",
    }

    def __init__(self, *, client=None):
        self._client = client

    def _get_html(self, uri):
        validate_official_source_uri(uri)
        own = self._client is None
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
            headers={
                "User-Agent": "GeoPilotAI/1.0 official-planning-document-discovery",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        current = uri
        try:
            for _ in range(MAX_REDIRECTS + 1):
                response = client.get(current)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise PlanningDocumentAcquisitionError("Official catalogue redirect missing Location.")
                    current = validate_official_source_uri(urljoin(current, location))
                    continue
                response.raise_for_status()
                if "html" not in response.headers.get("content-type", "").casefold():
                    raise PlanningDocumentAcquisitionError("Official planning catalogue did not return HTML.")
                return response.text, current
            raise PlanningDocumentAcquisitionError("Official planning catalogue exceeded redirect limit.")
        except httpx.HTTPError as exc:
            raise PlanningDocumentAcquisitionError("Official planning catalogue could not be retrieved.") from exc
        finally:
            if own:
                client.close()

    def _extract_gpp_candidates(self, html, base_uri):
        parser = _CatalogueLinkParser()
        parser.feed(html)
        out = []
        for title, href in parser.links:
            title = " ".join(title.split())
            if not title or not href:
                continue
            uri = urljoin(base_uri, href)
            if not urlparse(uri).path.casefold().endswith(".pdf"):
                continue
            if "gpp" not in title.casefold() and "garis panduan" not in title.casefold():
                continue
            try:
                validate_official_source_uri(uri)
            except PlanningDocumentAcquisitionError:
                continue
            out.append(PlanningDocumentCandidate(
                document_class="GPP", title=title, authority="PLANMalaysia",
                jurisdiction=None, source_uri=uri, provider=self.name,
                metadata={
                    "catalogue_uri": base_uri,
                    "catalogue_title": title,
                    "discovery_method": "official_catalogue_link",
                    "document_status": "unverified",
                },
            ))
        return out

    @staticmethod
    def _epublisiti_document_class(title):
        low = title.casefold()
        if "rancangan tempatan" in low:
            return "RT"
        if "rancangan struktur negeri" in low:
            return "RSN"
        if "rancangan kawasan khas" in low or "(rkk)" in low:
            return "RKK"
        return None

    @staticmethod
    def _epublisiti_status(title):
        low = title.casefold()
        signals = []
        for phrase, signal in (
            ("draf", "draft"), ("penggantian", "replacement"),
            ("pengubahan", "amendment"), ("kajian semula", "review"),
            ("publisiti", "publicity"), ("arkib", "archive"),
        ):
            if phrase in low:
                signals.append(signal)
        return {
            "document_status": "unverified",
            "status_signals": signals,
            "statutory_effect_verified": False,
        }

    def _state_slug(self, jurisdiction):
        if not jurisdiction:
            return None
        key = " ".join(jurisdiction.casefold().split())
        slug = self.STATE_SLUGS.get(key)
        if not slug:
            raise PlanningDocumentAcquisitionError(
                "Unsupported or unverified ePublisiti jurisdiction: " + jurisdiction
            )
        return slug

    def _epublisiti_urls(self, jurisdiction):
        slug = self._state_slug(jurisdiction)
        slugs = [slug] if slug else sorted(set(self.STATE_SLUGS.values()))
        return [
            self.EPUBLISITI_HOME_URL + "?search_category=epublisiti-plan-state-" + item
            for item in slugs
        ]

    def _extract_epublisiti(self, html, base_uri, requested_class, jurisdiction):
        parser = _CatalogueLinkParser()
        parser.feed(html)
        out = []
        for title, href in parser.links:
            title = " ".join(title.split())
            if not title or not href:
                continue
            if " on draf " in (" " + title.casefold() + " "):
                continue
            if self._epublisiti_document_class(title) != requested_class:
                continue
            uri = urljoin(base_uri, href)
            parsed = urlparse(uri)
            if parsed.path != "/epublisiti/article":
                continue
            article_id = parse_qs(parsed.query).get("id", [""])[0]
            if not article_id or article_id.endswith("-epublisiti"):
                continue
            try:
                validate_official_source_uri(uri)
            except PlanningDocumentAcquisitionError:
                continue
            out.append(PlanningDocumentCandidate(
                document_class=requested_class, title=title, authority="PLANMalaysia",
                jurisdiction=jurisdiction, source_uri=uri, provider=self.name,
                metadata={
                    "catalogue_uri": base_uri,
                    "catalogue_title": title,
                    "article_id": article_id,
                    "discovery_method": "epublisiti_state_catalogue",
                    "source_kind": "official_article_reference",
                    **self._epublisiti_status(title),
                },
            ))
        return out

    def _discover_gpp(self, query):
        found, seen = [], set()
        previous = None
        for page in range(1, self.MAX_GPP_PAGES + 1):
            html, final_uri = self._get_html(_with_page(self.GPP_CATALOGUE_URL, page))
            items = self._extract_gpp_candidates(html, final_uri)
            signature = tuple(sorted(_normalized_uri(x.source_uri) for x in items))
            if page > 1 and signature == previous:
                break
            previous = signature
            if page > 1 and not items:
                break
            for item in items:
                key = _normalized_uri(item.source_uri)
                if key not in seen:
                    seen.add(key)
                    found.append(item)
        return _rank_catalogue_candidates(found, query)

    def _discover_epublisiti(self, document_class, jurisdiction, query):
        found, seen = [], set()
        for catalogue_uri in self._epublisiti_urls(jurisdiction):
            html, final_uri = self._get_html(catalogue_uri)
            for item in self._extract_epublisiti(html, final_uri, document_class, jurisdiction):
                key = _normalized_uri(item.source_uri)
                if key not in seen:
                    seen.add(key)
                    found.append(item)
        return _rank_epublisiti_candidates(
            found,
            query,
            document_class=document_class,
            jurisdiction=jurisdiction,
        )


    def resolve_candidate_pdf_links(self, candidate):
        if candidate.provider != self.name:
            raise PlanningDocumentAcquisitionError(
                "Candidate provider is not supported by PLANMalaysia resolver."
            )

        validate_official_source_uri(candidate.source_uri)
        parsed = urlparse(candidate.source_uri)

        if parsed.path.casefold().endswith(".pdf"):
            return [candidate]

        if parsed.path != "/epublisiti/article":
            raise PlanningDocumentAcquisitionError(
                "Official candidate is neither a direct PDF nor a supported ePublisiti article."
            )

        html, final_uri = self._get_html(candidate.source_uri)
        parser = _DocumentLinkParser()
        parser.feed(html)

        found = []
        seen = set()
        for item in parser.links:
            href = item.get("href") or ""
            if not href:
                continue
            uri = urljoin(final_uri, href)
            if not urlparse(uri).path.casefold().endswith(".pdf"):
                continue
            try:
                validate_official_source_uri(uri)
            except PlanningDocumentAcquisitionError:
                continue

            key = _normalized_uri(uri)
            if key in seen:
                continue
            seen.add(key)

            title = _clean_resolved_title(
                item.get("context", ""),
                item.get("anchor_text", ""),
                candidate.title,
            )
            metadata = dict(candidate.metadata or {})
            metadata.update({
                "parent_article_uri": candidate.source_uri,
                "resolved_from_article": True,
                "resolution_method": "official_article_pdf_link",
                "resolved_link_text": item.get("anchor_text", ""),
                "resolved_context": item.get("context", ""),
            })

            found.append(
                PlanningDocumentCandidate(
                    document_class=candidate.document_class,
                    title=title,
                    authority=candidate.authority,
                    jurisdiction=candidate.jurisdiction,
                    source_uri=uri,
                    provider=candidate.provider,
                    metadata=metadata,
                )
            )

        if not found:
            raise PlanningDocumentAcquisitionError(
                "No official PDF link was found in the ePublisiti article."
            )
        return found

    def discover(self, *, document_class, jurisdiction, query):
        kind = document_class.strip().upper()
        if kind not in {"RFN", "RSN", "RT", "RKK", "GPP"}:
            raise PlanningDocumentAcquisitionError("Unsupported automatic planning document class: " + kind)
        if kind == "GPP":
            return self._discover_gpp(query)
        if kind in {"RT", "RSN", "RKK"}:
            return self._discover_epublisiti(kind, jurisdiction, query)
        return []

from app.schemas.planning_document import PlanningDocumentCreateRequest
from app.services.document_chunking import build_document_chunks
from app.services.document_indexing import build_document_embedding_index
from app.services.pdf_ingestion import ingest_registered_pdf, ingest_acquired_pdf
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

    ingestion = ingest_acquired_pdf(
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
