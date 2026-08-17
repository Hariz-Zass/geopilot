from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db import get_db_session
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db_session)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            code="authentication_required",
            message="A valid bearer access token is required.",
            status_code=401,
        )
    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise AppError(
            code="invalid_access_token",
            message="The access token is invalid or expired.",
            status_code=401,
        ) from exc

    user = session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise AppError(
            code="invalid_access_token",
            message="The access token is invalid or expired.",
            status_code=401,
        )
    return user
