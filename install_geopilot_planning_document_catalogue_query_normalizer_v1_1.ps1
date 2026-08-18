$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Svc="$Root\backend\app\services\planning_document_acquisition.py"
$Test="$Root\backend\tests\test_planning_document_catalogue_query_normalizer_v1_1.py"

if(!(Test-Path $Svc)){ throw "Missing required file: $Svc" }

Write-Host "============================================================"
Write-Host "GeoPilot Auto Research Catalogue Query Normalizer V1.1"
Write-Host "Jurisdiction-safe RT/RSN/RKK matching"
Write-Host "Preserve GPP V1 behavior"
Write-Host "NO DB SCHEMA CHANGE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\planning_document_catalogue_query_normalizer_v1_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Svc "$Backup\planning_document_acquisition.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_planning_document_catalogue_query_normalizer_v1_1.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Preflight"
    $Text=Get-Content $Svc -Raw
    if($Text -notmatch 'def _rank_catalogue_candidates\(items, query: str\)'){ throw "V1 ranker missing." }
    if($Text -match 'def _rank_epublisiti_candidates'){ throw "V1.1 already installed." }
    Write-Host "preflight_state=CONFIRMED"

    Write-Host "[1] Insert ePublisiti-specific ranker"

    $Anchor=@'
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
'@

    $Helper=@'

_EPUBLISITI_QUERY_NOISE = {
    "dasar", "cadangan", "pembangunan", "guna", "tanah", "syarat",
    "parameter", "polisi", "strategi", "hala", "tuju", "laporan",
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

def _rank_epublisiti_candidates(
    items,
    query: str,
    *,
    document_class: str,
    jurisdiction: str | None,
):
    terms = _catalogue_terms(query)
    jurisdiction_terms = _jurisdiction_terms(jurisdiction)
    identity_phrase = _epublisiti_identity_phrase(document_class)

    discriminators = [
        token for token in terms
        if token not in _CATALOGUE_CLASS_TERMS
        and token not in _EPUBLISITI_QUERY_NOISE
        and token not in jurisdiction_terms
    ]

    ranked = []
    for item in items:
        title_low = " ".join((item.title or "").casefold().split())

        # ePublisiti state pages may expose cross-state entries. Candidate
        # metadata alone is not treated as jurisdiction proof.
        if jurisdiction_terms and not all(token in title_low for token in jurisdiction_terms):
            continue

        if identity_phrase and identity_phrase not in title_low:
            continue

        matched_discriminators = [
            token for token in discriminators if token in title_low
        ]

        # If the user supplied a locality/topic/year discriminator, do not
        # silently substitute another RT/RKK/RSN.
        if discriminators and not matched_discriminators:
            continue

        base_score = _catalogue_candidate_score(item.title, query)
        directness = -sum(
            1 for signal in _EPUBLISITI_WRAPPER_SIGNALS if signal in title_low
        )
        score = (
            len(matched_discriminators),
            base_score[0],
            base_score[2],
            directness,
        )
        ranked.append((score, item.title.casefold(), item))

    ranked.sort(
        key=lambda x: (x[0][0], x[0][1], x[0][2], x[0][3]),
        reverse=True,
    )
    return [item for _, _, item in ranked]
'@

    if(-not $Text.Contains($Anchor)){ throw "Exact V1 ranker block not found." }
    $Text=$Text.Replace($Anchor,$Anchor+$Helper)

    $Call='        return _rank_catalogue_candidates(found, query)'
    $First=$Text.IndexOf($Call)
    if($First -lt 0){ throw "GPP rank call missing." }
    $Second=$Text.IndexOf($Call,$First+$Call.Length)
    if($Second -lt 0){ throw "ePublisiti rank call missing." }

    $Replacement=@'
        return _rank_epublisiti_candidates(
            found,
            query,
            document_class=document_class,
            jurisdiction=jurisdiction,
        )
'@
    $Text=$Text.Substring(0,$Second)+$Replacement+$Text.Substring($Second+$Call.Length)

    [System.IO.File]::WriteAllText($Svc,$Text,[System.Text.UTF8Encoding]::new($false))
    Write-Host "PATCHED: $Svc"

    Write-Host "[2] Install focused tests"
    $TestText=@'
from app.services.planning_document_acquisition import (
    PlanningDocumentCandidate,
    _rank_epublisiti_candidates,
    _rank_catalogue_candidates,
)

def c(title, cls, jurisdiction="Perak"):
    return PlanningDocumentCandidate(
        document_class=cls,
        title=title,
        authority="PLANMalaysia",
        jurisdiction=jurisdiction,
        source_uri="https://www.planmalaysia.gov.my/epublisiti/article?id=test",
        provider="planmalaysia_official",
        metadata={"document_status": "unverified"},
    )

def test_rsn_perak_natural_question_matches_state_identity():
    items = [
        c("LAPORAN TINJAUAN RANCANGAN STRUKTUR NEGERI PERAK 2040 (KAJIAN SEMULA)", "RSN"),
        c("Draf Rancangan Struktur Negeri Perak 2040", "RSN"),
    ]
    q = "Apakah dasar pembangunan negeri yang dinyatakan dalam Rancangan Struktur Negeri Perak? Sertakan sumber rasmi PLANMalaysia."
    ranked = _rank_epublisiti_candidates(items, q, document_class="RSN", jurisdiction="Perak")
    assert ranked
    assert all("PERAK" in x.title.upper() for x in ranked)
    assert ranked[0].title == "Draf Rancangan Struktur Negeri Perak 2040"

def test_rt_ipoh_does_not_substitute_other_perak_district():
    items = [
        c("Draf Rancangan Tempatan Daerah Perak Tengah 2030", "RT"),
        c("Draf Rancangan Tempatan Daerah Hulu Perak 2030", "RT"),
    ]
    q = "Apakah dasar dan cadangan guna tanah yang dinyatakan dalam Rancangan Tempatan bagi kawasan Ipoh?"
    ranked = _rank_epublisiti_candidates(items, q, document_class="RT", jurisdiction="Perak")
    assert ranked == []

def test_rt_specific_locality_matches():
    items = [
        c("Draf Rancangan Tempatan Daerah Perak Tengah 2030", "RT"),
        c("Draf Rancangan Tempatan Daerah Hulu Perak 2030", "RT"),
    ]
    q = "Apakah kandungan Rancangan Tempatan Daerah Perak Tengah 2030?"
    ranked = _rank_epublisiti_candidates(items, q, document_class="RT", jurisdiction="Perak")
    assert len(ranked) == 1
    assert "Perak Tengah" in ranked[0].title

def test_cross_state_catalogue_entry_is_rejected():
    items = [
        c("DRAF RANCANGAN TEMPATAN DAERAH SETIU 2035 (PENGGANTIAN)", "RT"),
        c("Draf Rancangan Tempatan Daerah Perak Tengah 2030", "RT"),
    ]
    q = "Rancangan Tempatan Daerah Perak Tengah 2030"
    ranked = _rank_epublisiti_candidates(items, q, document_class="RT", jurisdiction="Perak")
    assert len(ranked) == 1
    assert "Perak Tengah" in ranked[0].title

def test_generic_rkk_perak_fails_closed_without_explicit_perak_title():
    items = [
        c("RANCANGAN KAWASAN KHAS TASIK CHINI (PENGUBAHAN)", "RKK"),
        c("RANCANGAN KAWASAN KHAS RANGKAIAN EKOLOGI CENTRAL FOREST SPINE", "RKK"),
    ]
    q = "Apakah cadangan perancangan yang dinyatakan dalam Rancangan Kawasan Khas di negeri Perak?"
    ranked = _rank_epublisiti_candidates(items, q, document_class="RKK", jurisdiction="Perak")
    assert ranked == []

def test_gpp_v1_behavior_preserved():
    items = [
        c("(02) GP007 A(11)GPP Pembangunan Di Kawasan Bukit dan Tanah Tinggi", "GPP", jurisdiction=None),
        c("(22) GP012 GPP Papan Tanda Premis Perniagaan", "GPP", jurisdiction=None),
    ]
    ranked = _rank_catalogue_candidates(items, "bukit tanah tinggi")
    assert len(ranked) == 1
    assert "Bukit dan Tanah Tinggi" in ranked[0].title
'@
    [System.IO.File]::WriteAllText($Test,$TestText,[System.Text.UTF8Encoding]::new($false))

    Write-Host "[3] Syntax checks"
    docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py tests/test_planning_document_catalogue_query_normalizer_v1_1.py
    if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

    Write-Host "[4] Focused V1.1 regression"
    docker compose exec -T backend python -m pytest -q tests/test_planning_document_catalogue_query_normalizer_v1_1.py
    if($LASTEXITCODE-ne 0){ throw "Focused V1.1 regression failed." }

    Write-Host "[5] Preserve V1 regressions"
    foreach($T in @(
        "tests/test_planning_document_catalogue_query_normalizer_v1.py",
        "tests/test_planning_document_acquisition.py",
        "tests/test_planning_document_auto_research.py"
    )){
        if(Test-Path "$Root\backend\$T"){
            docker compose exec -T backend python -m pytest -q $T
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $T" }
        }
    }

    Write-Host "[6] Live provider verification"
    docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; p=PlanMalaysiaOfficialProvider(); tests=[('RT','Perak','Apakah dasar dan cadangan guna tanah yang dinyatakan dalam Rancangan Tempatan bagi kawasan Ipoh? Sertakan sumber rasmi PLANMalaysia.'),('RSN','Perak','Apakah dasar pembangunan negeri yang dinyatakan dalam Rancangan Struktur Negeri Perak? Sertakan sumber rasmi PLANMalaysia.'),('RKK','Perak','Apakah cadangan perancangan yang dinyatakan dalam Rancangan Kawasan Khas di negeri Perak? Sertakan sumber rasmi PLANMalaysia.')]; [(print(cls,'COUNT=',len(r:=p.discover(document_class=cls,jurisdiction=j,query=q))),[print(' ',x.title) for x in r[:5]]) for cls,j,q in tests]"
    if($LASTEXITCODE-ne 0){ throw "Live provider verification failed." }

    Write-Host "[7] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[8] Backend health"
    docker compose ps backend

    Write-Host "============================================================"
    Write-Host "AUTO RESEARCH CATALOGUE QUERY NORMALIZER V1.1 PASS"
    Write-Host "============================================================"
    Write-Host "GPP V1 behavior: PRESERVED"
    Write-Host "RSN state-identity matching: ENABLED"
    Write-Host "RT locality substitution: FORBIDDEN"
    Write-Host "RKK ambiguous-area substitution: FORBIDDEN"
    Write-Host "Cross-state ePublisiti title leakage: FILTERED"
    Write-Host "Draft/review/publicity statutory effect: NOT PROMOTED"
    Write-Host "Official-host/HTTPS/PDF safety: PRESERVED"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend change: NONE"
    Write-Host "Next gate: LIVE RSN E2E, THEN SPECIFIC RT/RKK WHEN CATALOGUE MATCH EXISTS"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring service/test backup."
    Copy-Item "$Backup\planning_document_acquisition.py" $Svc -Force
    if(Test-Path "$Backup\test_planning_document_catalogue_query_normalizer_v1_1.py"){
        Copy-Item "$Backup\test_planning_document_catalogue_query_normalizer_v1_1.py" $Test -Force
    } else {
        Remove-Item $Test -Force -ErrorAction SilentlyContinue
    }
    throw
}
