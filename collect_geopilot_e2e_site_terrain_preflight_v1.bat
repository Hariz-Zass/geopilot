@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "REPORT=geopilot_e2e_site_terrain_preflight_v1.txt"

echo ============================================================ > "%REPORT%"
echo GEOPILOT E2E SITE TERRAIN PREFLIGHT V1 >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo Working directory: %CD% >> "%REPORT%"
echo. >> "%REPORT%"

echo [1] SERVICE HEALTH >> "%REPORT%"
docker compose ps >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [2] RUNTIME TERRAIN CONFIG - VALUES HIDDEN >> "%REPORT%"
docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); print('CLIENT_ID configured:', bool(s.terrain_cdse_client_id)); print('CLIENT_SECRET configured:', bool(s.terrain_cdse_client_secret)); print('AUTO_ACQUISITION_ENABLED:', s.terrain_auto_acquisition_enabled); print('PROVIDER:', s.terrain_auto_provider); print('TARGET_CRS:', s.terrain_auto_target_crs)" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [3] AVAILABLE PROJECT / SITE CANDIDATES AND READY DEM COUNTS >> "%REPORT%"
docker compose exec -T backend python -c "from sqlalchemy import select, func; from app.db import SessionLocal; from app.models.user import User; from app.models.project import Project; from app.models.site import Site; from app.models.raster import RasterDataset; s=SessionLocal(); rows=s.execute(select(User.id,User.email,Project.id,Project.name,Site.id,Site.name,Site.is_active,Site.is_archived).join(Project,Project.owner_id==User.id).join(Site,Site.project_id==Project.id).where(Project.is_archived.is_(False),Site.is_archived.is_(False)).order_by(Project.created_at.desc(),Site.created_at.desc())).all(); print('candidate_count:',len(rows)); [print('USER',r[0],r[1],'| PROJECT',r[2],r[3],'| SITE',r[4],r[5],'| active=',r[6]) or print('  ready_dem_count=', s.scalar(select(func.count()).select_from(RasterDataset).where(RasterDataset.project_id==r[2],RasterDataset.site_id==r[4],RasterDataset.status=='ready',RasterDataset.is_archived.is_(False)))) for r in rows]; s.close()" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo [4] TERRAIN END-TO-END ENTRYPOINTS >> "%REPORT%"
findstr /n /i /c:"def acquire_site_dem_if_missing" /c:"def analyze" /c:"terrain" backend\app\services\terrain_acquisition.py backend\app\services\terrain_analysis.py >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo END PREFLIGHT - READ ONLY >> "%REPORT%"
echo No DB write, raster write, migration, frontend change, or credential output was performed. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"

type "%REPORT%"
echo.
echo Report saved to:
echo %CD%\%REPORT%
echo.
pause
exit /b 0
