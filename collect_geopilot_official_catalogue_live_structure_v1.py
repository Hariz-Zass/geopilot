from __future__ import annotations

import json
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx


URLS = [
    ("GPP_CATALOGUE", "https://www.planmalaysia.gov.my/main/document-list?type=garis-panduan-perancangan"),
    ("RT_EPUBLISITI", "https://www.planmalaysia.gov.my/epublisiti/article?id=rancangan-tempatan-epublisiti"),
    ("RSN_EPUBLISITI", "https://www.planmalaysia.gov.my/epublisiti/article?id=rancangan-struktur-negeri-epublisiti"),
    ("RKK_EPUBLISITI", "https://www.planmalaysia.gov.my/epublisiti/article?id=rancangan-kawasan-khas-epublisiti"),
    ("RFN4_MYPLAN", "https://myplan.planmalaysia.gov.my/portal-main/publication-details?id=7"),
]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attr_map = dict(attrs)
        self._href = attr_map.get("href")
        self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self._href is None:
            return
        text = " ".join("".join(self._text).split())
        self.links.append({"text": text, "href": self._href})
        self._href = None
        self._text = []


def interesting(text: str, href: str) -> bool:
    hay = f"{text} {href}".casefold()
    needles = (
        "pdf",
        "muat turun",
        "download",
        "rancangan tempatan",
        "rancangan struktur",
        "rancangan kawasan khas",
        "garis panduan",
        "gpp",
        "rfn",
        "rsn",
        "rt ",
        "rkk",
        "publication",
        "document",
        "epublisiti",
        "negeri",
        "perak",
        "selangor",
        "johor",
        "kuala lumpur",
        "putrajaya",
    )
    return any(n in hay for n in needles)


def fetch(client: httpx.Client, label: str, url: str) -> dict:
    response = client.get(url)
    response.raise_for_status()

    parser = LinkParser()
    parser.feed(response.text)

    links = []
    seen = set()
    for item in parser.links:
        absolute = urljoin(str(response.url), item["href"])
        key = (item["text"], absolute)
        if key in seen:
            continue
        seen.add(key)
        if interesting(item["text"], absolute):
            links.append(
                {
                    "text": item["text"][:180],
                    "href": absolute,
                }
            )

    return {
        "label": label,
        "requested_url": url,
        "status_code": response.status_code,
        "final_url": str(response.url),
        "content_type": response.headers.get("content-type"),
        "content_bytes": len(response.content),
        "all_anchor_count": len(parser.links),
        "interesting_link_count": len(links),
        "links": links[:250],
    }


def main() -> int:
    print("=" * 72)
    print("GEOPILOT OFFICIAL CATALOGUE LIVE STRUCTURE V1")
    print("READ ONLY")
    print("=" * 72)

    results = []
    errors = []

    headers = {
        "User-Agent": "GeoPilotAI/1.0 official-catalogue-audit",
        "Accept": "text/html,application/xhtml+xml",
    }

    with httpx.Client(
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        headers=headers,
    ) as client:
        for label, url in URLS:
            print()
            print(f"=== {label} ===")
            print(url)
            try:
                result = fetch(client, label, url)
                results.append(result)

                print(
                    f"status={result['status_code']} "
                    f"final={result['final_url']} "
                    f"bytes={result['content_bytes']} "
                    f"anchors={result['all_anchor_count']} "
                    f"interesting={result['interesting_link_count']}"
                )

                for item in result["links"]:
                    print(f"- {item['text']}")
                    print(f"  {item['href']}")

            except Exception as exc:
                errors.append(
                    {
                        "label": label,
                        "url": url,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(f"ERROR: {type(exc).__name__}: {exc}")

    print()
    print("=" * 72)
    print("MACHINE SUMMARY")
    print("=" * 72)
    print(
        json.dumps(
            {
                "results": results,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    print()
    print("=" * 72)
    print("AUDIT COMPLETE")
    print("No DB write, migration, source patch, or environment change.")
    print("=" * 72)

    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
