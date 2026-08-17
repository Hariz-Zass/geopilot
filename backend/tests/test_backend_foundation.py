from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app


def test_settings_parses_comma_separated_cors_origins() -> None:
    settings = Settings(CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173")
    assert settings.cors_origins == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )


def test_versioned_health_route_and_request_id() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/system/health", headers={"X-Request-ID": "test-123"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "geopilot-backend"}
    assert response.headers["X-Request-ID"] == "test-123"


def test_invalid_request_id_is_replaced() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/system/health", headers={"X-Request-ID": "bad id with spaces"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad id with spaces"
    assert len(response.headers["X-Request-ID"]) == 36


def test_structured_app_error_contains_request_id() -> None:
    app = create_app()
    router = APIRouter()

    @router.get("/_test/error")
    def raise_error() -> None:
        raise AppError(code="test_failure", message="Expected failure", status_code=409)

    app.include_router(router)
    client = TestClient(app)
    response = client.get("/_test/error", headers={"X-Request-ID": "err-1"})
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "test_failure",
            "message": "Expected failure",
            "details": None,
            "request_id": "err-1",
        }
    }


def test_not_found_uses_error_contract() -> None:
    client = TestClient(create_app())
    response = client.get("/does-not-exist", headers={"X-Request-ID": "missing-1"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"
    assert response.json()["error"]["request_id"] == "missing-1"


def test_openapi_contains_versioned_system_endpoint() -> None:
    client = TestClient(create_app())
    schema = client.get("/openapi.json").json()
    assert "/api/v1/system/health" in schema["paths"]
    assert "/api/v1/system/ready" in schema["paths"]
