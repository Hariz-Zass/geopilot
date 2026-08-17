from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.citations import router as citations_router
from app.api.v1.compliance_facts import router as compliance_facts_router
from app.api.v1.compliance_engine import router as compliance_engine_router
from app.api.v1.compliance_runs import router as compliance_runs_router
from app.api.v1.suitability import router as suitability_router
from app.api.v1.planning_runs import router as planning_runs_router
from app.api.v1.reports import router as reports_router
from app.api.v1.acceptance import router as acceptance_router
from app.api.v1.gis_features import router as gis_features_router
from app.api.v1.geometry import router as geometry_router
from app.api.v1.document_retrieval import router as document_retrieval_router
from app.api.v1.gis_analysis import router as gis_analysis_router
from app.api.v1.gis_layers import router as gis_layers_router
from app.api.v1.map_actions import router as map_actions_router
from app.api.v1.planning_documents import router as planning_documents_router
from app.api.v1.policy_references import router as policy_references_router
from app.api.v1.policy_criteria import router as policy_criteria_router
from app.api.v1.projects import router as projects_router
from app.api.v1.sites import router as sites_router
from app.api.v1.system import router as system_router
from app.api.v1.track_b import router as track_b_router
from app.api.v1.terrain import router as terrain_router

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(track_b_router)
api_router.include_router(terrain_router)
api_router.include_router(auth_router)
api_router.include_router(citations_router)
api_router.include_router(compliance_facts_router)
api_router.include_router(compliance_engine_router)
api_router.include_router(compliance_runs_router)
api_router.include_router(suitability_router)
api_router.include_router(planning_runs_router)
api_router.include_router(reports_router)
api_router.include_router(acceptance_router)
api_router.include_router(projects_router)
api_router.include_router(gis_layers_router)
api_router.include_router(gis_features_router)
api_router.include_router(gis_analysis_router)
api_router.include_router(geometry_router)
api_router.include_router(map_actions_router)
api_router.include_router(planning_documents_router)
api_router.include_router(policy_references_router)
api_router.include_router(policy_criteria_router)
api_router.include_router(document_retrieval_router)

api_router.include_router(sites_router)

