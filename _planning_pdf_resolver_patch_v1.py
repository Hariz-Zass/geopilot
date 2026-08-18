from pathlib import Path

service = Path("/app/app/services/planning_document_acquisition.py")
text = service.read_text(encoding="utf-8-sig")

if "class _DocumentLinkParser" in text and "def resolve_candidate_pdf_links" in text:
    print("SKIP: PDF resolver V1 already installed.")
    raise SystemExit(0)

insert_at = text.index("class PlanMalaysiaOfficialProvider:")

helpers = '''
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
'''

text = text[:insert_at] + helpers + "\n" + text[insert_at:]

needle = "    def discover(self, *, document_class, jurisdiction, query):\n"
if needle not in text:
    raise SystemExit("BLOCKED: provider discover marker not found.")

methods = '''
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

'''

text = text.replace(needle, methods + needle, 1)
service.write_text(text, encoding="utf-8")
print("PATCHED:", service)
