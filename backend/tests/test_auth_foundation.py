from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.security import decode_access_token, hash_password, verify_password
from app.db import get_db_session
from app.db.base import Base
from app.main import create_app
from app.models.user import User


@pytest.fixture()
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as test_client:
        yield test_client


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    password = "correct horse battery staple"
    encoded = hash_password(password)
    assert encoded != password
    assert encoded.startswith("$argon2id$")
    assert verify_password(password, encoded) is True
    assert verify_password("wrong password", encoded) is False


def test_register_normalizes_email_and_never_returns_password_hash(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Planner@Example.COM",
            "display_name": "  Planning   Officer  ",
            "password": "a-secure-password-123",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "planner@example.com"
    assert payload["display_name"] == "Planning Officer"
    assert "password" not in payload
    assert "password_hash" not in payload


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    data = {
        "email": "planner@example.com",
        "display_name": "Planner",
        "password": "a-secure-password-123",
    }
    assert client.post("/api/v1/auth/register", json=data).status_code == 201
    response = client.post("/api/v1/auth/register", json=data)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"


def test_login_returns_bearer_token_and_me_is_protected(client: TestClient) -> None:
    register = {
        "email": "planner@example.com",
        "display_name": "Planner",
        "password": "a-secure-password-123",
    }
    assert client.post("/api/v1/auth/register", json=register).status_code == 201

    unauthenticated = client.get("/api/v1/auth/me")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "authentication_required"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": register["email"], "password": register["password"]},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert 0 < body["expires_in"] <= 3600

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == register["email"]


def test_missing_and_wrong_password_share_invalid_credentials_contract(client: TestClient) -> None:
    missing = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "wrong"},
    )
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "invalid_credentials"

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "exists@example.com",
            "display_name": "Exists",
            "password": "a-secure-password-123",
        },
    )
    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "exists@example.com", "password": "wrong"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "invalid_credentials"


def test_inactive_user_cannot_login(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    password = "a-secure-password-123"
    with session_factory() as session:
        session.add(
            User(
                email="inactive@example.com",
                display_name="Inactive",
                password_hash=hash_password(password),
                is_active=False,
            )
        )
        session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": password},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_inactive"


def test_token_requires_expected_issuer_and_required_claims() -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "f4e7f84b-725f-4ac5-bf44-b78c0aa5017b",
            "iss": "wrong",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.auth_jwt_secret,
        algorithm=settings.auth_jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_short_jwt_secret_is_rejected() -> None:
    from pydantic import ValidationError
    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(AUTH_JWT_SECRET="too-short")


def test_auth_algorithm_is_server_locked_to_hs256() -> None:
    from pydantic import ValidationError
    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(AUTH_JWT_ALGORITHM="none")


def test_default_local_secret_is_rejected_for_production() -> None:
    from pydantic import ValidationError
    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            AUTH_JWT_SECRET="local-development-change-me-at-least-32-bytes",
        )
