$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Report = Join-Path $Root "geopilot_full_system_audit_v1.txt"

function Write-Section([string]$Title) {
    Add-Content -Path $Report -Value ""
    Add-Content -Path $Report -Value ("=" * 96)
    Add-Content -Path $Report -Value $Title
    Add-Content -Path $Report -Value ("=" * 96)
}

function Run-Capture([string]$Title, [scriptblock]$Command) {
    Write-Section $Title
    try {
        & $Command 2>&1 | ForEach-Object {
            $_ | Out-String -Width 5000 | Add-Content -Path $Report
        }
    }
    catch {
        Add-Content -Path $Report -Value ("ERROR: " + $_.Exception.Message)
    }
}

"" | Set-Content -Path $Report -Encoding UTF8

Add-Content $Report "GeoPilot AI - Full System Audit V1"
Add-Content $Report ("Generated: " + (Get-Date).ToString("s"))
Add-Content $Report ("Project root: " + $Root)
Add-Content $Report "MODE: READ ONLY"
Add-Content $Report "NO SOURCE PATCH / NO ENV CHANGE / NO DB WRITE / NO MIGRATION / NO SERVICE RECREATE"

Run-Capture "1. HOST / REPOSITORY STATE" {
    Write-Output ("PWD=" + (Get-Location).Path)
    git rev-parse --show-toplevel
    git rev-parse HEAD
    git branch --show-current
    git status --short
    git log -1 --oneline
}

Run-Capture "2. TOP-LEVEL PROJECT STRUCTURE" {
    Get-ChildItem -Force | Select-Object Mode,LastWriteTime,Length,Name | Format-Table -AutoSize
}

Run-Capture "3. DOCKER COMPOSE SERVICES" {
    docker compose ps
}

Run-Capture "4. DOCKER COMPOSE RESOLVED CONFIG - SAFE SUMMARY" {
    docker compose config --services
    Write-Output ""
    Write-Output "--- IMAGES / BUILDS / PORTS ---"
    docker compose config | Select-String -Pattern "^\s{2}[A-Za-z0-9_-]+:|image:|build:|ports:|container_name:|healthcheck:" -Context 0,2
}

Run-Capture "5. BACKEND RUNTIME CONFIG - SECRETS MASKED" {
    docker compose exec -T backend python -c @'
from app.core.config import get_settings
s=get_settings()
keys=[
"app_name","app_env","app_version","api_v1_prefix","log_level",
"document_storage_root","raster_storage_root",
"ai_provider","ai_fallback_provider",
"ollama_base_url","ollama_planning_model","openai_planning_model",
"embedding_provider","embedding_fallback_provider",
"ollama_embedding_model","openai_embedding_model",
]
for k in keys:
    if hasattr(s,k):
        print(f"{k}={getattr(s,k)}")
print("openai_api_key_configured=", bool(getattr(s,"openai_api_key",None)))
print("track_b_competition_mode_attribute_present=", hasattr(s,"track_b_competition_mode"))
'@
}

Run-Capture "6. ENV KEY NAMES - VALUES MASKED" {
    foreach($EnvPath in @(".env",".env.example")){
        if(Test-Path $EnvPath){
            Write-Output ("FILE: " + $EnvPath)
            Get-Content $EnvPath | ForEach-Object {
                $line=$_
                if($line -match '^\s*#' -or $line.Trim() -eq ''){
                    return
                }
                if($line -match '^\s*([^=]+)=(.*)$'){
                    $key=$matches[1].Trim()
                    $value=$matches[2]
                    if($key -match 'KEY|SECRET|TOKEN|PASSWORD|PASS|JWT'){
                        "$key=<REDACTED>"
                    } else {
                        "$key=$value"
                    }
                }
            }
        }
    }
}

Run-Capture "7. ALEMBIC / MIGRATION STATE" {
    docker compose exec -T backend alembic current
    docker compose exec -T backend alembic heads
    docker compose exec -T backend alembic history
}

Run-Capture "8. DATABASE TABLE INVENTORY - READ ONLY" {
    docker compose exec -T backend python -c @'
from sqlalchemy import inspect, text
from app.db.session import engine
with engine.connect() as c:
    i=inspect(c)
    tables=sorted(i.get_table_names())
    print("table_count=",len(tables))
    for t in tables:
        try:
            count=c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar_one()
        except Exception as e:
            count=f"ERROR:{e}"
        print(f"{t}: {count}")
'@
}

Run-Capture "9. BACKEND APP TREE" {
    Get-ChildItem backend\app -Recurse -File |
        Where-Object { $_.FullName -notmatch '__pycache__' } |
        ForEach-Object { $_.FullName.Substring($Root.Length+1) }
}

Run-Capture "10. FRONTEND SRC TREE" {
    Get-ChildItem frontend\src -Recurse -File |
        ForEach-Object { $_.FullName.Substring($Root.Length+1) }
}

Run-Capture "11. API ROUTERS / ENDPOINT DEFINITIONS" {
    Get-ChildItem backend\app\api -Recurse -File -Filter *.py |
        Select-String -Pattern '@router\.(get|post|put|patch|delete)|APIRouter\(' |
        ForEach-Object {
            "{0}:{1}: {2}" -f $_.Path.Substring($Root.Length+1),$_.LineNumber,$_.Line.Trim()
        }
}

Run-Capture "12. SQLALCHEMY MODELS" {
    Get-ChildItem backend\app\models -Recurse -File -Filter *.py |
        Select-String -Pattern '^class\s+\w+\(' |
        ForEach-Object {
            "{0}:{1}: {2}" -f $_.Path.Substring($Root.Length+1),$_.LineNumber,$_.Line.Trim()
        }
}

Run-Capture "13. AI / EMBEDDING PROVIDER IMPLEMENTATION" {
    $Files=@(
        "backend\app\services\ai_providers.py",
        "backend\app\services\provider_resilience.py",
        "backend\app\services\embedding_providers.py",
        "backend\app\services\grounded_synthesis.py"
    )
    foreach($f in $Files){
        if(Test-Path $f){
            Write-Output ""
            Write-Output ("### " + $f)
            Select-String -Path $f -Pattern "def |class |provider|fallback|openai|ollama|model" |
                ForEach-Object { "{0}: {1}" -f $_.LineNumber,$_.Line.Trim() }
        }
    }
}

Run-Capture "14. PLANNING ORCHESTRATOR / ROUTER / AUTO RESEARCH" {
    $Files=@(
        "backend\app\services\data_requirement_router.py",
        "backend\app\services\planning_orchestrator.py",
        "backend\app\services\planning_document_auto_research.py",
        "backend\app\services\planning_document_acquisition.py",
        "backend\app\services\document_retrieval.py"
    )
    foreach($f in $Files){
        if(Test-Path $f){
            Write-Output ""
            Write-Output ("### " + $f)
            Select-String -Path $f -Pattern "AUTO_RESEARCH|documents.search|terrain.site_summary|route_question|infer_document_classes|infer_jurisdiction|discover\(|acquire_candidate|ingest_acquired_document|search_documents|RFN|RSN|RKK|GPP|RT" |
                ForEach-Object { "{0}: {1}" -f $_.LineNumber,$_.Line.Trim() }
        }
    }
}

Run-Capture "15. TRACK B / CLOSED-EVIDENCE RESIDUAL AUDIT" {
    Get-ChildItem backend\app,frontend\src -Recurse -File |
        Where-Object { $_.FullName -notmatch '__pycache__|frontend\\dist' } |
        Select-String -Pattern "CLOSED EVIDENCE|closed-evidence|closed evidence|closed_evidence|organizer-only|organizer_only|external acquisition|TRACK_B_COMPETITION_MODE|track_b_competition_mode" |
        ForEach-Object {
            "{0}:{1}: {2}" -f $_.Path.Substring($Root.Length+1),$_.LineNumber,$_.Line.Trim()
        }
}

Run-Capture "16. TRACK B SOURCE SUMMARY" {
    $Files=@(
        "backend\app\services\track_b.py",
        "backend\app\services\track_b_ai.py",
        "backend\app\services\track_b_acceptance.py",
        "backend\app\services\track_b_workflow.py",
        "frontend\src\pages\TrackBWorkspacePage.tsx"
    )
    foreach($f in $Files){
        if(Test-Path $f){
            Write-Output ""
            Write-Output ("### " + $f)
            Select-String -Path $f -Pattern "def |function |Build decision brief|decision|evidence|acceptance|competition|organizer|planner|runPlannerDecision|planningRunsApi|decisionWorkspace|terrain" |
                ForEach-Object { "{0}: {1}" -f $_.LineNumber,$_.Line.Trim() }
        }
    }
}

Run-Capture "17. TERRAIN / SATELLITE / GIS SERVICES" {
    Get-ChildItem backend\app\services -File -Filter *.py |
        Where-Object { $_.Name -match 'terrain|satellite|raster|gis|map|geometry' } |
        ForEach-Object {
            Write-Output ""
            Write-Output ("### " + $_.FullName.Substring($Root.Length+1))
            Select-String -Path $_.FullName -Pattern "def |class |provider|CDSE|Sentinel|DEM|terrain|raster|site_summary|manual" |
                ForEach-Object { "{0}: {1}" -f $_.LineNumber,$_.Line.Trim() }
        }
}

Run-Capture "18. DOCUMENT PIPELINE SERVICES" {
    $Files=@(
        "backend\app\services\planning_documents.py",
        "backend\app\services\pdf_ingestion.py",
        "backend\app\services\document_chunking.py",
        "backend\app\services\document_indexing.py",
        "backend\app\services\document_retrieval.py"
    )
    foreach($f in $Files){
        if(Test-Path $f){
            Write-Output ""
            Write-Output ("### " + $f)
            Select-String -Path $f -Pattern "def |source_kind|ingestion_state|extraction_state|index_state|OCR|chunk|embedding|citation|checksum|review_state" |
                ForEach-Object { "{0}: {1}" -f $_.LineNumber,$_.Line.Trim() }
        }
    }
}

Run-Capture "19. FRONTEND ROUTING / PAGE INVENTORY" {
    Get-ChildItem frontend\src -Recurse -File -Include *.tsx,*.ts |
        Select-String -Pattern "Route|path=|TrackBWorkspacePage|Planning|Dashboard|Projects|Site" |
        ForEach-Object {
            "{0}:{1}: {2}" -f $_.Path.Substring($Root.Length+1),$_.LineNumber,$_.Line.Trim()
        }
}

Run-Capture "20. TEST INVENTORY" {
    if(Test-Path backend\tests){
        Get-ChildItem backend\tests -File -Filter test_*.py |
            Sort-Object Name |
            Select-Object Name,Length |
            Format-Table -AutoSize
    }
}

Run-Capture "21. PYTEST COLLECTION SUMMARY" {
    docker compose exec -T backend python -m pytest --collect-only -q
}

Run-Capture "22. RECENT PROJECT ARTIFACTS / AUDITS" {
    if(Test-Path artifacts){
        Get-ChildItem artifacts -Force |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 80 Mode,LastWriteTime,Name |
            Format-Table -AutoSize
    }
}

Run-Capture "23. SOURCE MODIFICATION SUMMARY" {
    git diff --stat
    Write-Output ""
    git diff --name-only
}

Run-Capture "24. HIGH-LEVEL CAPABILITY MARKERS" {
    $patterns=@(
        "AUTO_RESEARCH_QUESTION_ROUTER_V1",
        "AUTO_RESEARCH_EVIDENCE_BRIDGE_V1",
        "DECISION_WORKSPACE_TERRAIN_ROUTER_V1",
        "terrain.site_summary",
        "PlanMalaysiaOfficialProvider",
        "ingest_acquired_pdf",
        "embeddinggemma",
        "source_kind.*acquired",
        "RFN automatic acquisition",
        "fail-closed"
    )
    foreach($p in $patterns){
        Write-Output ("--- PATTERN: " + $p)
        Get-ChildItem backend\app,frontend\src -Recurse -File |
            Where-Object { $_.FullName -notmatch '__pycache__|frontend\\dist' } |
            Select-String -Pattern $p |
            Select-Object -First 30 |
            ForEach-Object {
                "{0}:{1}: {2}" -f $_.Path.Substring($Root.Length+1),$_.LineNumber,$_.Line.Trim()
            }
    }
}

Write-Section "25. AUDIT SAFETY SUMMARY"
Add-Content $Report "Source write: NONE"
Add-Content $Report "Environment write: NONE"
Add-Content $Report "Database write: NONE"
Add-Content $Report "Migration: NONE"
Add-Content $Report "Service restart/recreate: NONE"
Add-Content $Report "Purpose: architecture/state visibility only"

Write-Host "============================================================"
Write-Host "GEOPILOT FULL SYSTEM AUDIT V1 COMPLETE"
Write-Host "============================================================"
Write-Host "REPORT: $Report"
Write-Host "Source change: NONE"
Write-Host "ENV change: NONE"
Write-Host "DB write: NONE"
Write-Host "Migration: NONE"
Write-Host "Service restart: NONE"
Write-Host "============================================================"
