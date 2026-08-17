from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db import get_db_session
from app.models.user import User
from app.schemas.auth import AccessTokenResponse, LoginRequest, UserRegisterRequest, UserResponse
from app.services.auth import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    authenticate_user,
    issue_access_token,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserRegisterRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> User:
    try:
        return register_user(session, payload)
    except EmailAlreadyRegisteredError as exc:
        raise AppError(
            code="email_already_registered",
            message="An account with this email already exists.",
            status_code=409,
        ) from exc


@router.post("/login", response_model=AccessTokenResponse)
def login(
    payload: LoginRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> AccessTokenResponse:
    try:
        user = authenticate_user(session, payload)
    except InvalidCredentialsError as exc:
        raise AppError(
            code="invalid_credentials",
            message="Email or password is incorrect.",
            status_code=401,
        ) from exc
    except InactiveUserError as exc:
        raise AppError(
            code="account_inactive",
            message="This account is inactive.",
            status_code=403,
        ) from exc

    token, expires_in = issue_access_token(user)
    return AccessTokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user
