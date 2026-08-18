$ErrorActionPreference="Stop"
Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer Phase 2A"
Write-Host "GIS Conversion Foundation + Import Plan"
Write-Host "NO DB WRITE / NO MIGRATION"
Write-Host "============================================================"

$root=(Get-Location).Path
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root "artifacts\smart_organizer_phase2a_backup_$stamp"
$log=Join-Path $root "artifacts\smart_organizer_phase2a_result.txt"
$dockerfile=Join-Path $root "backend\Dockerfile"
$api=Join-Path $root "backend\app\api\v1\track_b.py"
$service=Join-Path $root "backend\app\services\track_b_smart_import.py"
$test=Join-Path $root "backend\tests\test_track_b_smart_import_phase2a.py"
$servicePayload=Join-Path $root "track_b_smart_import.py.txt"
$testPayload=Join-Path $root "test_track_b_smart_import_phase2a.py.txt"

foreach($p in @($dockerfile,$api,$servicePayload,$testPayload)){if(-not(Test-Path $p)){throw "Required file missing: $p"}}
New-Item -ItemType Directory -Force $backup|Out-Null
Copy-Item $dockerfile (Join-Path $backup "Dockerfile") -Force
Copy-Item $api (Join-Path $backup "track_b.py") -Force
if(Test-Path $service){Copy-Item $service (Join-Path $backup "track_b_smart_import.py") -Force}
if(Test-Path $test){Copy-Item $test (Join-Path $backup "test_track_b_smart_import_phase2a.py") -Force}

function Restore-Backup{
 Copy-Item (Join-Path $backup "Dockerfile") $dockerfile -Force
 Copy-Item (Join-Path $backup "track_b.py") $api -Force
 if(Test-Path(Join-Path $backup "track_b_smart_import.py")){Copy-Item (Join-Path $backup "track_b_smart_import.py") $service -Force}elseif(Test-Path $service){Remove-Item $service -Force}
 if(Test-Path(Join-Path $backup "test_track_b_smart_import_phase2a.py")){Copy-Item (Join-Path $backup "test_track_b_smart_import_phase2a.py") $test -Force}elseif(Test-Path $test){Remove-Item $test -Force}
}

try{
 Write-Host "BACKUP: $backup"
 Write-Host "[0] Preflight"
 $apiText=Get-Content $api -Raw
 if(-not $apiText.Contains('@router.post("/organizer-intake/inspect")')){throw "Smart Organizer inspect endpoint missing."}
 if($apiText.Contains("SMART_ORGANIZER_PHASE2A")){throw "Phase 2A already present."}
 $df=Get-Content $dockerfile -Raw
 $m=[regex]::Match($df,'(?m)^FROM\s+.+$')
 if(-not $m.Success){throw "Dockerfile FROM not found."}
 Write-Host "preflight_state=CONFIRMED"

 Write-Host "[1] Add persistent GDAL CLI to backend image"
 if($df -notmatch 'GEOPILOT_SMART_IMPORT_GDAL'){
  $block=@'
# GEOPILOT_SMART_IMPORT_GDAL
RUN if command -v apt-get >/dev/null 2>&1; then \
      apt-get update && apt-get install -y --no-install-recommends gdal-bin && rm -rf /var/lib/apt/lists/*; \
    elif command -v apk >/dev/null 2>&1; then \
      apk add --no-cache gdal-tools; \
    else \
      echo "Unsupported package manager" >&2; exit 1; \
    fi
'@
  $df=$df.Replace($m.Value,$m.Value+"`r`n"+$block)
  Set-Content $dockerfile $df -Encoding UTF8
 }

 Write-Host "[2] Install conversion service + test"
 Copy-Item $servicePayload $service -Force
 Copy-Item $testPayload $test -Force

 Write-Host "[3] Patch Track B API"
 $apiText=Get-Content $api -Raw
 $imp='from app.services.track_b_smart_intake import inspect_organizer_package'
 if(-not $apiText.Contains($imp)){throw "API import anchor missing."}
 $apiText=$apiText.Replace($imp,$imp+"`r`nfrom app.services.track_b_smart_import import prepare_import_plan")
 $anchor='@router.post("/organizer-intake/inspect")'
 $idx=$apiText.IndexOf($anchor)
 if($idx -lt 0){throw "Inspect route anchor missing."}
 $route=@'
# SMART_ORGANIZER_PHASE2A
@router.post("/organizer-intake/prepare")
async def organizer_intake_prepare(
    project_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        return await prepare_import_plan(files)
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc


'@
 $apiText=$apiText.Insert($idx,$route)
 Set-Content $api $apiText -Encoding UTF8

 Write-Host "[4] Build backend image"
 docker compose build backend
 if($LASTEXITCODE-ne 0){throw "Backend build failed."}

 Write-Host "[5] Recreate backend"
 docker compose up -d --force-recreate backend
 if($LASTEXITCODE-ne 0){throw "Backend recreate failed."}
 Start-Sleep -Seconds 8
 docker compose ps backend

 Write-Host "[6] GDAL runtime"
 docker compose exec -T backend sh -lc "ogr2ogr --version && ogrinfo --version"
 if($LASTEXITCODE-ne 0){throw "GDAL runtime check failed."}

 Write-Host "[7] Syntax"
 docker compose exec -T backend python -m py_compile /app/app/services/track_b_smart_import.py /app/app/api/v1/track_b.py
 if($LASTEXITCODE-ne 0){throw "Syntax failed."}

 Write-Host "[8] Phase 2A tests"
 docker compose exec -T backend python -m pytest -q tests/test_track_b_smart_import_phase2a.py
 if($LASTEXITCODE-ne 0){throw "Phase 2A test failed."}

 Write-Host "[9] Preserve Smart Organizer regressions"
 docker compose exec -T backend python -m pytest -q tests/test_track_b_smart_organizer_intake_v1.py tests/test_track_b_smart_organizer_zip_v1_2_2.py tests/test_track_b_smart_organizer_gis_bundle_v1_3.py tests/test_track_b_smart_organizer_format_coverage_v1_3_3.py
 if($LASTEXITCODE-ne 0){throw "Smart Organizer regression failed."}

 Write-Host "[10] Full backend regression"
 docker compose exec -T backend python -m pytest -q
 if($LASTEXITCODE-ne 0){throw "Full backend regression failed."}

 Write-Host "[11] DB safety"
 $db=@'
from app.db import get_session_factory
from sqlalchemy import text
with get_session_factory()() as db:
    print("alembic_revision=",db.execute(text("SELECT version_num FROM alembic_version")).scalar())
    print("gis_layers=",db.execute(text("SELECT COUNT(*) FROM gis_layers")).scalar())
    print("gis_features=",db.execute(text("SELECT COUNT(*) FROM gis_features")).scalar())
'@
 $db|docker compose exec -T -w /app backend python -
 if($LASTEXITCODE-ne 0){throw "DB safety failed."}

 @"
============================================================
SMART ORGANIZER PHASE 2A PASS
============================================================
Persistent GDAL conversion runtime: ENABLED
MapInfo TAB conversion preview: ENABLED
ESRI Shapefile conversion preview: ENABLED
GeoPackage layer conversion preview: ENABLED
Normalized output CRS: EPSG:4326
Import-plan endpoint: /organizer-intake/prepare
Database writes: NONE
Migration: NONE
Next gate: LIVE PHASE 2A PREPARE IMPORT PLAN
============================================================
"@|Tee-Object -FilePath $log
 Write-Host "RESULT SAVED TO: $log"
}
catch{
 Write-Host ""
 Write-Host "INSTALL FAILED - restoring backup."
 Restore-Backup
 throw
}
