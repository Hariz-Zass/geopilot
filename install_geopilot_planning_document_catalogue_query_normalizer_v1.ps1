$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Svc="$Root\backend\app\services\planning_document_acquisition.py"
$Test="$Root\backend\tests\test_planning_document_catalogue_query_normalizer_v1.py"
if(!(Test-Path $Svc)){ throw "Missing required file: $Svc" }

Write-Host "============================================================"
Write-Host "GeoPilot Auto Research Catalogue Query Normalizer V1"
Write-Host "Natural-language question -> official catalogue matching"
Write-Host "GPP + RT + RSN + RKK"
Write-Host "NO DB SCHEMA CHANGE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\planning_document_catalogue_query_normalizer_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Svc "$Backup\planning_document_acquisition.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_planning_document_catalogue_query_normalizer_v1.py" }
Write-Host "BACKUP: $Backup"

try {
  Write-Host "[0] Preflight literal matching gate"
  $t=Get-Content $Svc -Raw
  $literal='tokens = " ".join(query.casefold().split()).split()'
  if(([regex]::Matches($t,[regex]::Escape($literal))).Count -ne 2){
    throw "Expected exactly two literal catalogue token match blocks."
  }
  Write-Host "literal_matching_state=CONFIRMED"

  Write-Host "[1] Patch shared query normalizer + ranking"
  $PatchPath="$Root\backend\_patch_catalogue_query_normalizer_v1.py"
  @'
from pathlib import Path

p = Path("/app/app/services/planning_document_acquisition.py")
t = p.read_text(encoding="utf-8-sig")

anchor = 'def _with_page(uri,page):\n    x=urlparse(uri); q=parse_qs(x.query,keep_blank_values=True); q["page"]=[str(page)]\n    return urlunparse(x._replace(query=urlencode(q,doseq=True)))\n'

helper = r'''
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
'''

if "_CATALOGUE_STOPWORDS" not in t:
    if anchor not in t:
        raise SystemExit("NORMALIZER_ANCHOR_NOT_FOUND")
    t = t.replace(anchor, anchor + "\n" + helper + "\n", 1)

old = '        tokens = " ".join(query.casefold().split()).split()\n        return [x for x in found if all(t in x.title.casefold() for t in tokens)] if tokens else found\n'
if t.count(old) != 2:
    raise SystemExit(f"EXPECTED_TWO_LITERAL_MATCH_BLOCKS_FOUND_{t.count(old)}")
t = t.replace(old, '        return _rank_catalogue_candidates(found, query)\n')

p.write_text(t, encoding="utf-8")
print("PATCHED:", p)
'@ | Set-Content $PatchPath -Encoding UTF8

  try {
    docker compose exec -T backend python /app/_patch_catalogue_query_normalizer_v1.py
    if($LASTEXITCODE-ne 0){ throw "Catalogue normalizer patch failed." }
  } finally {
    Remove-Item $PatchPath -Force -ErrorAction SilentlyContinue
  }

  Write-Host "[2] Install focused regression tests"
  @'
from app.services.planning_document_acquisition import PlanningDocumentCandidate, _catalogue_terms, _rank_catalogue_candidates

def c(title, cls="GPP"):
    return PlanningDocumentCandidate(
        document_class=cls,
        title=title,
        authority="PLANMalaysia",
        jurisdiction=None,
        source_uri="https://www.planmalaysia.gov.my/uploads/test.pdf",
        provider="planmalaysia_official",
        metadata={},
    )

def test_full_question_reduces_to_meaningful_terms():
    q=("Apakah garis panduan pembangunan di kawasan bukit dan tanah tinggi? "
       "Nyatakan syarat atau parameter yang dinyatakan dalam GPP rasmi PLANMalaysia "
       "dan sertakan sumber bukti. Jangan reka maklumat yang tidak terdapat dalam dokumen.")
    terms=_catalogue_terms(q)
    for expected in ("pembangunan","bukit","tanah","tinggi","syarat","parameter"):
        assert expected in terms
    for rejected in ("apakah","nyatakan","sumber","bukti","planmalaysia","jangan","reka","maklumat"):
        assert rejected not in terms

def test_full_question_ranks_correct_gpp_first():
    q=("Apakah garis panduan pembangunan di kawasan bukit dan tanah tinggi? "
       "Nyatakan syarat atau parameter yang dinyatakan dalam GPP rasmi PLANMalaysia dan sertakan sumber bukti.")
    items=[
        c("(02) GP007 A(11)GPP Pembangunan Di Kawasan Bukit dan Tanah Tinggi"),
        c("(18) GP007 A (1) GPP Pemuliharaan Dan Pembangunan Kawasan Sensitif Alam Sekitar (KSAS)"),
        c("(22) GP012 GPP Papan Tanda Premis Perniagaan"),
    ]
    ranked=_rank_catalogue_candidates(items,q)
    assert ranked
    assert "Bukit dan Tanah Tinggi" in ranked[0].title

def test_short_query_still_matches():
    items=[c("(02) GP007 A(11)GPP Pembangunan Di Kawasan Bukit dan Tanah Tinggi"),c("(22) GP012 GPP Papan Tanda Premis Perniagaan")]
    ranked=_rank_catalogue_candidates(items,"bukit tanah tinggi")
    assert len(ranked)==1

def test_zero_overlap_fails_closed():
    assert _rank_catalogue_candidates([c("(22) GP012 GPP Papan Tanda Premis Perniagaan")],"bukit tanah tinggi")==[]

def test_generic_rt_question_matches_title_terms():
    rt=c("Rancangan Tempatan Daerah Ipoh 2035",cls="RT")
    ranked=_rank_catalogue_candidates([rt],"Apakah densiti yang dinyatakan dalam Rancangan Tempatan Daerah Ipoh 2035?")
    assert ranked==[rt]
'@ | Set-Content $Test -Encoding UTF8

  Write-Host "[3] Syntax checks"
  docker compose exec -T backend python -m py_compile app/services/planning_document_acquisition.py tests/test_planning_document_catalogue_query_normalizer_v1.py
  if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

  Write-Host "[4] Focused normalizer regression"
  docker compose exec -T backend python -m pytest -q tests/test_planning_document_catalogue_query_normalizer_v1.py
  if($LASTEXITCODE-ne 0){ throw "Focused normalizer regression failed." }

  Write-Host "[5] Preserve acquisition regressions"
  foreach($T in @("tests/test_planning_document_acquisition.py","tests/test_planning_document_auto_research.py")){
    if(Test-Path "$Root\backend\$T"){
      docker compose exec -T backend python -m pytest -q $T
      if($LASTEXITCODE-ne 0){ throw "Regression failed: $T" }
    }
  }

  Write-Host "[6] Live provider verification with full user question"
  docker compose exec -T backend python -c "from app.services.planning_document_acquisition import PlanMalaysiaOfficialProvider; q='Apakah garis panduan pembangunan di kawasan bukit dan tanah tinggi? Nyatakan syarat atau parameter yang dinyatakan dalam GPP rasmi PLANMalaysia dan sertakan sumber bukti. Jangan reka maklumat yang tidak terdapat dalam dokumen.'; r=PlanMalaysiaOfficialProvider().discover(document_class='GPP',jurisdiction=None,query=q); print('COUNT=',len(r)); [print(x.title, x.source_uri) for x in r[:5]]; assert r and 'Bukit dan Tanah Tinggi' in r[0].title"
  if($LASTEXITCODE-ne 0){ throw "Live provider full-question verification failed." }

  Write-Host "[7] Recreate backend"
  docker compose up -d --no-deps --force-recreate backend
  if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }
  Start-Sleep -Seconds 5

  Write-Host "[8] Backend health"
  docker compose ps backend

  Write-Host "[9] Runtime verification"
  docker compose exec -T backend python -c "from app.services.planning_document_acquisition import _catalogue_terms; q='Apakah garis panduan pembangunan di kawasan bukit dan tanah tinggi? Nyatakan syarat atau parameter yang dinyatakan dalam GPP rasmi PLANMalaysia dan sertakan sumber bukti.'; print('TERMS=',_catalogue_terms(q)); assert {'pembangunan','bukit','tanah','tinggi'}.issubset(set(_catalogue_terms(q))); print('runtime_catalogue_normalizer=PASS')"
  if($LASTEXITCODE-ne 0){ throw "Runtime normalizer verification failed." }

  Write-Host "============================================================"
  Write-Host "AUTO RESEARCH CATALOGUE QUERY NORMALIZER V1 PASS"
  Write-Host "============================================================"
  Write-Host "Natural-language question normalization: ENABLED"
  Write-Host "Literal all-token title matching: REMOVED"
  Write-Host "Meaningful topical-overlap ranking: ENABLED"
  Write-Host "GPP matching: IMPROVED"
  Write-Host "RT/RSN/RKK matching: IMPROVED"
  Write-Host "Zero-overlap candidate acceptance: FORBIDDEN"
  Write-Host "Official host / HTTPS / PDF safety: PRESERVED"
  Write-Host "Auto acquisition pipeline: PRESERVED"
  Write-Host "DB schema change: NONE"
  Write-Host "Migration: NONE"
  Write-Host "Frontend change: NONE"
  Write-Host "Next gate: LIVE GPP QUESTION E2E"
  Write-Host "============================================================"
}
catch {
  Write-Host "INSTALL FAILED - restoring service/test backup."
  Copy-Item "$Backup\planning_document_acquisition.py" $Svc -Force
  if(Test-Path "$Backup\test_planning_document_catalogue_query_normalizer_v1.py"){
    Copy-Item "$Backup\test_planning_document_catalogue_query_normalizer_v1.py" $Test -Force
  } else {
    Remove-Item $Test -Force -ErrorAction SilentlyContinue
  }
  throw
}
