from fastapi import APIRouter, Response, status

from app.db import verify_database_readiness

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    """Process liveness only; it does not claim database readiness."""
    return {"status": "ok", "service": "geopilot-backend"}


@router.get("/ready")
def ready(response: Response) -> dict[str, object]:
    """Fail closed unless spatial/vector database capabilities are available."""
    result = verify_database_readiness()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result.public_payload()
