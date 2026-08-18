from pathlib import Path
import re

service = Path("/app/app/services/planning_document_acquisition.py")
text = service.read_text(encoding="utf-8-sig")

if "class PlanMalaysiaOfficialProvider:" not in text:
    raise SystemExit("BLOCKED: PlanMalaysiaOfficialProvider missing.")

# Preserve everything before provider class, including GPP helper parser/functions.
start = text.index("class PlanMalaysiaOfficialProvider:")
prefix = text[:start]

provider = r"""
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
        tokens = " ".join(query.casefold().split()).split()
        return [x for x in found if all(t in x.title.casefold() for t in tokens)] if tokens else found

    def _discover_epublisiti(self, document_class, jurisdiction, query):
        found, seen = [], set()
        for catalogue_uri in self._epublisiti_urls(jurisdiction):
            html, final_uri = self._get_html(catalogue_uri)
            for item in self._extract_epublisiti(html, final_uri, document_class, jurisdiction):
                key = _normalized_uri(item.source_uri)
                if key not in seen:
                    seen.add(key)
                    found.append(item)
        tokens = " ".join(query.casefold().split()).split()
        return [x for x in found if all(t in x.title.casefold() for t in tokens)] if tokens else found

    def discover(self, *, document_class, jurisdiction, query):
        kind = document_class.strip().upper()
        if kind not in {"RFN", "RSN", "RT", "RKK", "GPP"}:
            raise PlanningDocumentAcquisitionError("Unsupported automatic planning document class: " + kind)
        if kind == "GPP":
            return self._discover_gpp(query)
        if kind in {"RT", "RSN", "RKK"}:
            return self._discover_epublisiti(kind, jurisdiction, query)
        return []
"""

service.write_text(prefix + provider + "\n", encoding="utf-8")
print("PATCHED:", service)
