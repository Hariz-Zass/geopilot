from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, UserRegisterRequest


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InactiveUserError(Exception):
    pass


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email.strip().lower()))


def register_user(session: Session, request: UserRegisterRequest) -> User:
    user = User(
        email=str(request.email).lower(),
        display_name=request.display_name,
        password_hash=hash_password(request.password),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise EmailAlreadyRegisteredError from exc
    session.refresh(user)
    return user


def authenticate_user(session: Session, request: LoginRequest) -> User:
    user = get_user_by_email(session, str(request.email))
    # Do not reveal whether the account exists.
    if user is None or not verify_password(request.password, user.password_hash):
        raise InvalidCredentialsError
    if not user.is_active:
        raise InactiveUserError
    return user


def issue_access_token(user: User) -> tuple[str, int]:
    token, expires_at = create_access_token(user.id)
    from datetime import datetime, timezone

    expires_in = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    return token, expires_in
