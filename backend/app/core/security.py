from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_password_hash = PasswordHasher()


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    expires_at: datetime


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID) -> tuple[str, datetime]:
    settings = get_settings()
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.auth_access_token_minutes)
    payload = {
        "sub": str(user_id),
        "iss": settings.auth_issuer,
        "iat": issued_at,
        "exp": expires_at,
    }
    encoded = jwt.encode(
        payload,
        settings.auth_jwt_secret,
        algorithm=settings.auth_jwt_algorithm,
    )
    return encoded, expires_at


def decode_access_token(token: str) -> AccessTokenClaims:
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.auth_jwt_secret,
        algorithms=[settings.auth_jwt_algorithm],
        issuer=settings.auth_issuer,
        options={"require": ["sub", "iss", "iat", "exp"]},
    )
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (ValueError, TypeError, KeyError) as exc:
        raise InvalidTokenError("invalid subject") from exc

    exp = payload["exp"]
    expires_at = datetime.fromtimestamp(float(exp), tz=timezone.utc)
    return AccessTokenClaims(user_id=user_id, expires_at=expires_at)
