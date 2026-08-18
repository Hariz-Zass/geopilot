@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "REPORT=geopilot_e2e_site_candidates_v2.txt"

echo ============================================================ > "%REPORT%"
echo GEOPILOT E2E SITE CANDIDATES V2 >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo. >> "%REPORT%"

docker compose exec -T backend python -c "from sqlalchemy import select,func; from app.db import get_session_factory; from app.models.project import Project; from app.models.site import Site; from app.models.raster import RasterDataset; s=get_session_factory()(); rows=s.execute(select(Project.id,Project.name,Site.id,Site.name,Site.is_active).join(Site,Site.project_id==Project.id).where(Project.is_archived.is_(False),Site.is_archived.is_(False)).order_by(Project.created_at.desc(),Site.created_at.desc())).all(); print('candidate_count:',len(rows)); [print('PROJECT_ID=',r[0],'| PROJECT=',r[1],'| SITE_ID=',r[2],'| SITE=',r[3],'| active=',r[4],'| ready_dem=',s.scalar(select(func.count()).select_from(RasterDataset).where(RasterDataset.project_id==r[0],RasterDataset.site_id==r[2],RasterDataset.status=='ready',RasterDataset.is_archived.is_(False)))) for r in rows]; s.close()" >> "%REPORT%" 2>&1

echo. >> "%REPORT%"
echo ============================================================ >> "%REPORT%"
echo READ ONLY - NO DB OR RASTER WRITE >> "%REPORT%"
echo ============================================================ >> "%REPORT%"

type "%REPORT%"
echo.
echo Report saved to:
echo %CD%\%REPORT%
echo.
pause
