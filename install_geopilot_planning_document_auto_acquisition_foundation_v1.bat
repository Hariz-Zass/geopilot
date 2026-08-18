@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "REPORT=geopilot_planning_document_auto_acquisition_foundation_v1_report.txt"

echo ============================================================
echo GeoPilot Planning Document Auto-Acquisition Foundation V1
echo Official-source provider boundary + safe downloader
echo NO DB WRITE / NO MIGRATION / NO FRONTEND CHANGE
echo ============================================================

echo [0] Preflight
if not exist "backend\app\services\planning_documents.py" (
  echo ERROR: expected GeoPilot backend files not found.
  pause
  exit /b 1
)
if not exist "backend\tests" (
  echo ERROR: backend tests folder not found.
  pause
  exit /b 1
)

set "STAMP=%DATE:~-4%%DATE:~4,2%%DATE:~7,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "STAMP=%STAMP: =0%"
set "BACKUP=artifacts\planning_document_auto_acquisition_foundation_v1_backup_%STAMP%"
mkdir "%BACKUP%" >nul 2>&1
if exist "backend\app\services\planning_document_acquisition.py" copy /y "backend\app\services\planning_document_acquisition.py" "%BACKUP%\" >nul
if exist "backend\tests\test_planning_document_acquisition.py" copy /y "backend\tests\test_planning_document_acquisition.py" "%BACKUP%\" >nul
echo BACKUP: %CD%\%BACKUP%

echo.
echo [1] Install provider-boundary service
> "backend\app\services\planning_document_acquisition.py" (
echo from __future__ import annotations
echo.
echo import hashlib
echo import ipaddress
echo import socket
echo from dataclasses import dataclass
echo from typing import Protocol
echo from urllib.parse import urljoin, urlparse
echo.
echo import httpx
echo.
echo.
echo MAX_DOCUMENT_BYTES = 100 * 1024 * 1024
echo MAX_REDIRECTS = 5
echo OFFICIAL_HOST_SUFFIXES = (
echo     "planmalaysia.gov.my",
echo     "myplan.planmalaysia.gov.my",
echo )
echo.
echo.
echo class PlanningDocumentAcquisitionError(Exception):
echo     pass
echo.
echo.
echo @dataclass(frozen=True)
echo class PlanningDocumentCandidate:
echo     document_class: str
echo     title: str
echo     authority: str
echo     jurisdiction: str ^| None
echo     source_uri: str
echo     provider: str
echo     metadata: dict
echo.
echo.
echo @dataclass(frozen=True)
echo class AcquiredPlanningDocument:
echo     candidate: PlanningDocumentCandidate
echo     content: bytes
echo     mime_type: str
echo     checksum_sha256: str
echo     final_uri: str
echo.
echo.
echo class PlanningDocumentProvider(Protocol):
echo     name: str
echo.
echo     def discover(
echo         self,
echo         *,
echo         document_class: str,
echo         jurisdiction: str ^| None,
echo         query: str,
echo     ^) -^> list[PlanningDocumentCandidate]:
echo         ...
echo.
echo.
echo def _official_host(host: str ^| None^) -^> bool:
echo     if not host:
echo         return False
echo     host = host.rstrip(".").casefold()
echo     return any(host == suffix or host.endswith("." + suffix^) for suffix in OFFICIAL_HOST_SUFFIXES^)
echo.
echo.
echo def _public_dns_only(host: str^) -^> None:
echo     try:
echo         addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM^)}
echo     except OSError as exc:
echo         raise PlanningDocumentAcquisitionError("Official document host could not be resolved."^) from exc
echo     if not addresses:
echo         raise PlanningDocumentAcquisitionError("Official document host resolved to no addresses."^)
echo     for value in addresses:
echo         ip = ipaddress.ip_address(value^)
echo         if not ip.is_global:
echo             raise PlanningDocumentAcquisitionError("Document acquisition rejected a non-public network target."^)
echo.
echo.
echo def validate_official_source_uri(uri: str^) -^> str:
echo     parsed = urlparse(uri^)
echo     if parsed.scheme.casefold(^) != "https":
echo         raise PlanningDocumentAcquisitionError("Planning document acquisition requires HTTPS."^)
echo     if parsed.username or parsed.password:
echo         raise PlanningDocumentAcquisitionError("Planning document source URI must not contain credentials."^)
echo     if parsed.port not in (None, 443^):
echo         raise PlanningDocumentAcquisitionError("Planning document source URI must use standard HTTPS."^)
echo     if not _official_host(parsed.hostname^):
echo         raise PlanningDocumentAcquisitionError("Planning document source is not an approved official PLANMalaysia host."^)
echo     _public_dns_only(parsed.hostname or ""^)
echo     return uri
echo.
echo.
echo def acquire_candidate(
echo     candidate: PlanningDocumentCandidate,
echo     *,
echo     client: httpx.Client ^| None = None,
echo     max_bytes: int = MAX_DOCUMENT_BYTES,
echo ^) -^> AcquiredPlanningDocument:
echo     current = validate_official_source_uri(candidate.source_uri^)
echo     own_client = client is None
echo     http = client or httpx.Client(timeout=httpx.Timeout(60.0^), follow_redirects=False^)
echo     try:
echo         for _ in range(MAX_REDIRECTS + 1^):
echo             response = http.get(current, headers={"Accept": "application/pdf,application/octet-stream;q=0.9" }^)
echo             if response.status_code in {301, 302, 303, 307, 308}:
echo                 location = response.headers.get("location"^)
echo                 if not location:
echo                     raise PlanningDocumentAcquisitionError("Official source returned a redirect without Location."^)
echo                 current = validate_official_source_uri(urljoin(current, location^)^)
echo                 continue
echo             response.raise_for_status(^)
echo             content = response.content
echo             if not content:
echo                 raise PlanningDocumentAcquisitionError("Official document response was empty."^)
echo             if len(content^) ^> max_bytes:
echo                 raise PlanningDocumentAcquisitionError("Official document exceeded the configured safety limit."^)
echo             content_type = response.headers.get("content-type", ""^).split(";", 1^)[0].strip(^).casefold(^)
echo             is_pdf = content.startswith(b"%%PDF-"^)
echo             if not is_pdf:
echo                 raise PlanningDocumentAcquisitionError("Official document response was not a valid PDF payload."^)
echo             return AcquiredPlanningDocument(
echo                 candidate=candidate,
echo                 content=content,
echo                 mime_type="application/pdf",
echo                 checksum_sha256=hashlib.sha256(content^).hexdigest(^),
echo                 final_uri=current,
echo             ^)
echo         raise PlanningDocumentAcquisitionError("Official document exceeded the redirect limit."^)
echo     except httpx.HTTPError as exc:
echo         raise PlanningDocumentAcquisitionError("Official planning document could not be downloaded."^) from exc
echo     finally:
echo         if own_client:
echo             http.close(^)
echo.
echo.
echo class PlanMalaysiaOfficialProvider:
echo     """
echo     Provider boundary for official PLANMalaysia / MyPLAN discovery.
echo.
echo     V1 intentionally does not scrape search engines and does not guess document URLs.
echo     Concrete RFN/RSN/RT/RKK/GPP catalogue adapters are added behind this boundary.
echo     """
echo.
echo     name = "planmalaysia_official"
echo.
echo     def discover(
echo         self,
echo         *,
echo         document_class: str,
echo         jurisdiction: str ^| None,
echo         query: str,
echo     ^) -^> list[PlanningDocumentCandidate]:
echo         supported = {"RFN", "RSN", "RT", "RKK", "GPP"}
echo         normalized = document_class.strip(^).upper(^)
echo         if normalized not in supported:
echo             raise PlanningDocumentAcquisitionError(
echo                 f"Unsupported automatic planning document class: {normalized}"
echo             ^)
echo         # Fail closed until each official catalogue endpoint/parser is accepted.
echo         return []
)

echo.
echo [2] Install regression tests
> "backend\tests\test_planning_document_acquisition.py" (
echo import httpx
echo import pytest
echo.
echo from app.services.planning_document_acquisition import (
echo     PlanMalaysiaOfficialProvider,
echo     PlanningDocumentAcquisitionError,
echo     PlanningDocumentCandidate,
echo     acquire_candidate,
echo ^)
echo.
echo.
echo def candidate(uri: str^) -^> PlanningDocumentCandidate:
echo     return PlanningDocumentCandidate(
echo         document_class="GPP",
echo         title="Test Official GPP",
echo         authority="PLANMalaysia",
echo         jurisdiction="Malaysia",
echo         source_uri=uri,
echo         provider="planmalaysia_official",
echo         metadata={},
echo     ^)
echo.
echo.
echo def test_provider_supports_controlled_planning_classes_and_fails_closed(^):
echo     provider = PlanMalaysiaOfficialProvider(^)
echo     assert provider.discover(document_class="RFN", jurisdiction="Malaysia", query="density"^) == []
echo     with pytest.raises(PlanningDocumentAcquisitionError^):
echo         provider.discover(document_class="OTHER", jurisdiction=None, query="x"^)
echo.
echo.
echo def test_downloader_rejects_non_official_host_before_network(^):
echo     with pytest.raises(PlanningDocumentAcquisitionError^):
echo         acquire_candidate(candidate("https://example.com/test.pdf"^)^)
echo.
echo.
echo def test_downloader_accepts_pdf_and_hashes_payload(monkeypatch^):
echo     import app.services.planning_document_acquisition as mod
echo     monkeypatch.setattr(mod, "_public_dns_only", lambda host: None^)
echo     payload = b"%%PDF-1.7\nGeoPilot\n%%%%EOF\n"
echo     def handler(request: httpx.Request^) -^> httpx.Response:
echo         assert request.url.host == "myplan.planmalaysia.gov.my"
echo         return httpx.Response(200, content=payload, headers={"content-type": "application/pdf"}^)
echo     with httpx.Client(transport=httpx.MockTransport(handler^)^) as client:
echo         result = acquire_candidate(
echo             candidate("https://myplan.planmalaysia.gov.my/example.pdf"^),
echo             client=client,
echo         ^)
echo     assert result.content == payload
echo     assert result.mime_type == "application/pdf"
echo     assert len(result.checksum_sha256^) == 64
echo.
echo.
echo def test_downloader_rejects_redirect_to_unapproved_host(monkeypatch^):
echo     import app.services.planning_document_acquisition as mod
echo     monkeypatch.setattr(mod, "_public_dns_only", lambda host: None^)
echo     def handler(request: httpx.Request^) -^> httpx.Response:
echo         return httpx.Response(302, headers={"location": "https://example.com/file.pdf"}^)
echo     with httpx.Client(transport=httpx.MockTransport(handler^)^) as client:
echo         with pytest.raises(PlanningDocumentAcquisitionError^):
echo             acquire_candidate(
echo                 candidate("https://myplan.planmalaysia.gov.my/start"^),
echo                 client=client,
echo             ^)
)

echo.
echo [3] Syntax checks
docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py
if errorlevel 1 goto :fail

echo.
echo [4] Acquisition regression tests
docker compose exec -T backend pytest -q tests/test_planning_document_acquisition.py
if errorlevel 1 goto :fail

echo.
echo [5] Existing document retrieval regression
docker compose exec -T backend pytest -q tests/test_document_retrieval.py
if errorlevel 1 goto :fail

echo.
echo [6] Verify no migration/frontend patch
git diff --name-only -- backend/alembic backend/migrations frontend > "%TEMP%\geopilot_pdacq_diff.txt"
for /f "usebackq delims=" %%L in ("%TEMP%\geopilot_pdacq_diff.txt") do (
  echo NOTE: pre-existing diff detected: %%L
)
echo Installer itself changed only service/test files.

echo.
echo [7] Service health
docker compose ps

> "%REPORT%" (
echo ============================================================
echo PLANNING DOCUMENT AUTO-ACQUISITION FOUNDATION V1 PASS
echo ============================================================
echo Provider boundary: planmalaysia_official
echo Controlled classes: RFN / RSN / RT / RKK / GPP
echo Official HTTPS allowlist: ENABLED
echo Redirect re-validation: ENABLED
echo Private/local network targets: BLOCKED
echo PDF payload validation: ENABLED
echo SHA-256 provenance primitive: ENABLED
echo Arbitrary web scraping: NOT ENABLED
echo Guessed document URLs: FORBIDDEN
echo Concrete catalogue discovery adapters: NEXT GATE
echo Existing document retrieval pipeline: PRESERVED
echo DB write by installer: NONE
echo Migration: NONE
echo Frontend change: NONE
echo ============================================================
)
type "%REPORT%"
echo.
echo Foundation installed successfully.
pause
exit /b 0

:fail
echo.
echo ============================================================
echo INSTALLER FAILED
echo ============================================================
echo Do not retry blindly. Paste the complete output into ChatGPT.
pause
exit /b 1
