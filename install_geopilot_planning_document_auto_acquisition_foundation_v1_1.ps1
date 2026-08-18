$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service = Join-Path $Root "backend\app\services\planning_document_acquisition.py"
$Tests = Join-Path $Root "backend\tests\test_planning_document_acquisition.py"

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root "artifacts\planning_document_auto_acquisition_foundation_v1_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
if (Test-Path $Service) { Copy-Item $Service (Join-Path $Backup "planning_document_acquisition.py") }
if (Test-Path $Tests) { Copy-Item $Tests (Join-Path $Backup "test_planning_document_acquisition.py") }

Write-Host "============================================================"
Write-Host "GeoPilot Planning Document Auto-Acquisition Foundation V1.1"
Write-Host "Recovery for BAT echo/parser corruption"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"
Write-Host ""

$serviceContent = @'
from __future__ import annotations

import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlparse

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


class PlanMalaysiaOfficialProvider:
    """
    Provider boundary for official PLANMalaysia / MyPLAN discovery.

    V1.1 deliberately fails closed. It does not scrape search engines,
    guess document URLs, or persist anything to the database.
    Concrete RFN/RSN/RT/RKK/GPP catalogue adapters are the next gate.
    """

    name = "planmalaysia_official"

    def discover(
        self,
        *,
        document_class: str,
        jurisdiction: str | None,
        query: str,
    ) -> list[PlanningDocumentCandidate]:
        supported = {"RFN", "RSN", "RT", "RKK", "GPP"}
        normalized = document_class.strip().upper()

        if normalized not in supported:
            raise PlanningDocumentAcquisitionError(
                f"Unsupported automatic planning document class: {normalized}"
            )

        return []
'@

$testContent = @'
import httpx
import pytest

from app.services.planning_document_acquisition import (
    PlanMalaysiaOfficialProvider,
    PlanningDocumentAcquisitionError,
    PlanningDocumentCandidate,
    acquire_candidate,
)


def candidate(uri: str) -> PlanningDocumentCandidate:
    return PlanningDocumentCandidate(
        document_class="GPP",
        title="Test Official GPP",
        authority="PLANMalaysia",
        jurisdiction="Malaysia",
        source_uri=uri,
        provider="planmalaysia_official",
        metadata={},
    )


def test_provider_supports_controlled_planning_classes_and_fails_closed():
    provider = PlanMalaysiaOfficialProvider()

    assert (
        provider.discover(
            document_class="RFN",
            jurisdiction="Malaysia",
            query="density",
        )
        == []
    )

    with pytest.raises(PlanningDocumentAcquisitionError):
        provider.discover(
            document_class="OTHER",
            jurisdiction=None,
            query="x",
        )


def test_downloader_rejects_non_official_host_before_network():
    with pytest.raises(PlanningDocumentAcquisitionError):
        acquire_candidate(candidate("https://example.com/test.pdf"))


def test_downloader_accepts_pdf_and_hashes_payload(monkeypatch):
    import app.services.planning_document_acquisition as mod

    monkeypatch.setattr(
        mod,
        "_public_dns_only",
        lambda host: None,
    )

    payload = b"%PDF-1.7\nGeoPilot\n%%EOF\n"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "myplan.planmalaysia.gov.my"
        return httpx.Response(
            200,
            content=payload,
            headers={"content-type": "application/pdf"},
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        result = acquire_candidate(
            candidate(
                "https://myplan.planmalaysia.gov.my/example.pdf"
            ),
            client=client,
        )

    assert result.content == payload
    assert result.mime_type == "application/pdf"
    assert len(result.checksum_sha256) == 64


def test_downloader_rejects_redirect_to_unapproved_host(monkeypatch):
    import app.services.planning_document_acquisition as mod

    monkeypatch.setattr(
        mod,
        "_public_dns_only",
        lambda host: None,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={
                "location": "https://example.com/file.pdf",
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(PlanningDocumentAcquisitionError):
            acquire_candidate(
                candidate(
                    "https://myplan.planmalaysia.gov.my/start"
                ),
                client=client,
            )
'@

Set-Content -Path $Service -Value $serviceContent -Encoding UTF8
Set-Content -Path $Tests -Value $testContent -Encoding UTF8

Write-Host "[1] Rewrote provider-boundary service and tests safely"
Write-Host ""

Write-Host "[2] Syntax checks"
docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) {
    throw "Syntax check failed."
}

Write-Host ""
Write-Host "[3] Acquisition regression tests"
docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) {
    throw "Planning document acquisition tests failed."
}

Write-Host ""
Write-Host "[4] Existing document retrieval regression"
docker compose exec -T backend python -m pytest -q tests/test_document_retrieval.py
if ($LASTEXITCODE -ne 0) {
    throw "Existing document retrieval regression failed."
}

Write-Host ""
Write-Host "[5] Import verification"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider, OFFICIAL_HOST_SUFFIXES; print('provider=',PlanMalaysiaOfficialProvider.name); print('hosts=',OFFICIAL_HOST_SUFFIXES)"
if ($LASTEXITCODE -ne 0) {
    throw "Provider import verification failed."
}

Write-Host ""
Write-Host "[6] Service health"
docker compose ps
if ($LASTEXITCODE -ne 0) {
    throw "Service health check failed."
}

Write-Host ""
Write-Host "============================================================"
Write-Host "PLANNING DOCUMENT AUTO-ACQUISITION FOUNDATION V1.1 PASS"
Write-Host "============================================================"
Write-Host "Provider boundary: planmalaysia_official"
Write-Host "Controlled classes: RFN / RSN / RT / RKK / GPP"
Write-Host "Official HTTPS allowlist: ENABLED"
Write-Host "Redirect re-validation: ENABLED"
Write-Host "Private/local network targets: BLOCKED"
Write-Host "PDF payload validation: ENABLED"
Write-Host "SHA-256 provenance primitive: ENABLED"
Write-Host "Arbitrary web scraping: NOT ENABLED"
Write-Host "Guessed document URLs: FORBIDDEN"
Write-Host "Concrete catalogue discovery adapters: NEXT GATE"
Write-Host "Existing document retrieval pipeline: PRESERVED"
Write-Host "DB write by installer: NONE"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "============================================================"
