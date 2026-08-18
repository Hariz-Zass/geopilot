$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$SvcPath="$Root\backend\app\services\planning_document_acquisition.py"
$TestPath="$Root\backend\tests\test_planning_document_catalogue_query_normalizer_v1_2.py"

if(!(Test-Path $SvcPath)){ throw "Missing required file: $SvcPath" }

Write-Host "============================================================"
Write-Host "GeoPilot Auto Research Catalogue Query Normalizer V1.2"
Write-Host "Locality-aware RT/RSN/RKK matching + safe jurisdiction fallback"
Write-Host "Preserve GPP V1 behavior"
Write-Host "NO DB SCHEMA CHANGE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir="$Root\artifacts\planning_document_catalogue_query_normalizer_v1_2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
Copy-Item $SvcPath "$BackupDir\planning_document_acquisition.py"
if(Test-Path $TestPath){ Copy-Item $TestPath "$BackupDir\test_planning_document_catalogue_query_normalizer_v1_2.py" }
Write-Host "BACKUP: $BackupDir"

try {
    Write-Host "[0] Confirm V1.1 rollback + V1 baseline"
    $SourceText=Get-Content $SvcPath -Raw
    if($SourceText -notmatch 'def _rank_catalogue_candidates\(items, query: str\)'){
        throw "V1 shared ranker missing."
    }
    if($SourceText -match 'def _rank_epublisiti_candidates'){
        throw "Unexpected residual V1.1 ranker found. Stop for inspection."
    }
    if(([regex]::Matches($SourceText,'return _rank_catalogue_candidates\(found, query\)')).Count -ne 2){
        throw "Expected exactly two V1 ranker call sites."
    }
    Write-Host "rollback_state=CONFIRMED"

    Write-Host "[1] Add locality-aware ePublisiti ranker"

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
'@

    if(-not $SourceText.Contains($Anchor)){
        throw "Exact V1 ranker block not found."
    }
    $SourceText=$SourceText.Replace($Anchor,$Anchor+$Helper)

    $Call='        return _rank_catalogue_candidates(found, query)'
    $FirstIndex=$SourceText.IndexOf($Call)
    if($FirstIndex -lt 0){ throw "GPP V1 rank call missing." }
    $SecondIndex=$SourceText.IndexOf($Call,$FirstIndex+$Call.Length)
    if($SecondIndex -lt 0){ throw "ePublisiti V1 rank call missing." }

    $Replacement=@'
        return _rank_epublisiti_candidates(
            found,
            query,
            document_class=document_class,
            jurisdiction=jurisdiction,
        )
'@

    $SourceText=$SourceText.Substring(0,$SecondIndex)+$Replacement+$SourceText.Substring($SecondIndex+$Call.Length)
    [System.IO.File]::WriteAllText($SvcPath,$SourceText,[System.Text.UTF8Encoding]::new($false))
    Write-Host "PATCHED: $SvcPath"

    Write-Host "[2] Install focused V1.2 regressions"

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


def test_rsn_perak_generic_question_matches_explicit_state_titles():
    items = [
        c("LAPORAN TINJAUAN RANCANGAN STRUKTUR NEGERI PERAK 2040 (KAJIAN SEMULA)", "RSN"),
        c("Draf Rancangan Struktur Negeri Perak 2040", "RSN"),
    ]
    q = "Apakah dasar pembangunan negeri yang dinyatakan dalam Rancangan Struktur Negeri Perak?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RSN", jurisdiction="Perak"
    )
    assert len(ranked) == 2
    assert ranked[0].title == "Draf Rancangan Struktur Negeri Perak 2040"


def test_rt_ipoh_does_not_substitute_other_locality():
    items = [
        c("Draf Rancangan Tempatan Daerah Perak Tengah 2030", "RT"),
        c("Draf Rancangan Tempatan Daerah Hulu Perak 2030", "RT"),
    ]
    q = "Apakah dasar dan cadangan guna tanah dalam Rancangan Tempatan bagi kawasan Ipoh?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RT", jurisdiction="Perak"
    )
    assert ranked == []


def test_rt_perak_tengah_requires_tengah_not_merely_perak_or_year():
    items = [
        c("Draf Rancangan Tempatan Daerah Perak Tengah 2030", "RT"),
        c("Draf Rancangan Tempatan Daerah Hulu Perak 2030", "RT"),
    ]
    q = "Apakah kandungan Rancangan Tempatan Daerah Perak Tengah 2030?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RT", jurisdiction="Perak"
    )
    assert len(ranked) == 1
    assert "Perak Tengah" in ranked[0].title


def test_rt_specific_locality_can_match_without_state_name_in_title():
    items = [
        c("Rancangan Tempatan Daerah Manjung 2040", "RT"),
        c("Rancangan Tempatan Daerah Hulu Perak 2030", "RT"),
    ]
    q = "Apakah kandungan Rancangan Tempatan Daerah Manjung 2040?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RT", jurisdiction="Perak"
    )
    assert len(ranked) == 1
    assert "Manjung" in ranked[0].title


def test_generic_rt_perak_fails_closed_when_title_does_not_prove_state():
    items = [
        c("Rancangan Tempatan Daerah Manjung 2040", "RT"),
        c("Rancangan Tempatan Daerah Setiu 2035", "RT"),
    ]
    q = "Apakah kandungan Rancangan Tempatan di negeri Perak?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RT", jurisdiction="Perak"
    )
    assert ranked == []


def test_generic_rkk_perak_fails_closed_without_state_in_title():
    items = [
        c("Rancangan Kawasan Khas Tasik Chini (Pengubahan)", "RKK"),
        c("Rancangan Kawasan Khas Rangkaian Ekologi Central Forest Spine", "RKK"),
    ]
    q = "Apakah cadangan dalam Rancangan Kawasan Khas di negeri Perak?"
    ranked = _rank_epublisiti_candidates(
        items, q, document_class="RKK", jurisdiction="Perak"
    )
    assert ranked == []


def test_gpp_v1_ranker_behavior_is_preserved():
    items = [
        c("(02) GP007 A(11)GPP Pembangunan Di Kawasan Bukit dan Tanah Tinggi", "GPP", jurisdiction=None),
        c("(22) GP012 GPP Papan Tanda Premis Perniagaan", "GPP", jurisdiction=None),
    ]
    ranked = _rank_catalogue_candidates(items, "bukit tanah tinggi")
    assert len(ranked) == 1
    assert "Bukit dan Tanah Tinggi" in ranked[0].title
'@

    [System.IO.File]::WriteAllText($TestPath,$TestText,[System.Text.UTF8Encoding]::new($false))

    Write-Host "[3] Syntax checks"
    docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py tests/test_planning_document_catalogue_query_normalizer_v1_2.py
    if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

    Write-Host "[4] Focused V1.2 regression"
    docker compose exec -T backend python -m pytest -q tests/test_planning_document_catalogue_query_normalizer_v1_2.py
    if($LASTEXITCODE-ne 0){ throw "Focused V1.2 regression failed." }

    Write-Host "[5] Preserve V1 regressions"
    foreach($Regression in @(
        "tests/test_planning_document_catalogue_query_normalizer_v1.py",
        "tests/test_planning_document_acquisition.py",
        "tests/test_planning_document_auto_research.py"
    )){
        if(Test-Path "$Root\backend\$Regression"){
            docker compose exec -T backend python -m pytest -q $Regression
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $Regression" }
        }
    }

    Write-Host "[6] Live provider verification"
    docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; p=PlanMalaysiaOfficialProvider(); qs=[('RT','Perak','Apakah dasar dan cadangan guna tanah yang dinyatakan dalam Rancangan Tempatan bagi kawasan Ipoh? Sertakan sumber rasmi PLANMalaysia.'),('RSN','Perak','Apakah dasar pembangunan negeri yang dinyatakan dalam Rancangan Struktur Negeri Perak? Sertakan sumber rasmi PLANMalaysia.'),('RKK','Perak','Apakah cadangan perancangan yang dinyatakan dalam Rancangan Kawasan Khas di negeri Perak? Sertakan sumber rasmi PLANMalaysia.'),('RT','Perak','Apakah kandungan Rancangan Tempatan Daerah Perak Tengah 2030?')]; [(print(cls,'|',q,'| COUNT=',len(r:=p.discover(document_class=cls,jurisdiction=j,query=q))),[print(' ',x.title) for x in r[:5]]) for cls,j,q in qs]"
    if($LASTEXITCODE-ne 0){ throw "Live provider verification failed." }

    Write-Host "[7] Static safety verification"
    $VerifyText=Get-Content $SvcPath -Raw
    if($VerifyText -notmatch 'def _rank_epublisiti_candidates'){ throw "V1.2 ranker missing." }
    if(([regex]::Matches($VerifyText,'return _rank_catalogue_candidates\(found, query\)')).Count -ne 1){
        throw "GPP V1 rank call was not preserved exactly once."
    }
    if($VerifyText -notmatch 'return _rank_epublisiti_candidates\('){
        throw "ePublisiti V1.2 rank call missing."
    }
    Write-Host "static_catalogue_contract=PASS"

    Write-Host "[8] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[9] Backend health"
    docker compose ps backend

    Write-Host "============================================================"
    Write-Host "AUTO RESEARCH CATALOGUE QUERY NORMALIZER V1.2 PASS"
    Write-Host "============================================================"
    Write-Host "GPP V1 behavior: PRESERVED"
    Write-Host "RSN state identity matching: ENABLED"
    Write-Host "RT specific locality matching: ENABLED"
    Write-Host "RT wrong-locality substitution: FORBIDDEN"
    Write-Host "Year-only false match: FORBIDDEN"
    Write-Host "Generic RT without title-level state proof: FAIL-CLOSED"
    Write-Host "Generic RKK without title-level state proof: FAIL-CLOSED"
    Write-Host "Cross-state ePublisiti substitution: FAIL-CLOSED"
    Write-Host "Draft/review/publicity statutory effect: NOT PROMOTED"
    Write-Host "Official host / HTTPS / PDF safety: PRESERVED"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend change: NONE"
    Write-Host "Next gate: LIVE RSN E2E + SPECIFIC RT PERAK TENGAH E2E"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring service/test backup."
    Copy-Item "$BackupDir\planning_document_acquisition.py" $SvcPath -Force
    if(Test-Path "$BackupDir\test_planning_document_catalogue_query_normalizer_v1_2.py"){
        Copy-Item "$BackupDir\test_planning_document_catalogue_query_normalizer_v1_2.py" $TestPath -Force
    } else {
        Remove-Item $TestPath -Force -ErrorAction SilentlyContinue
    }
    throw
}
