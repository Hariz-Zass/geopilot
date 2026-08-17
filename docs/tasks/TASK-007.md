# TASK-007 — User / Authentication Foundation

## Objective
Introduce the first persistent application domain: authenticated user identity. The authentication layer must protect later project-scoped operations without introducing Project or Site yet.

## Implemented
- `User` ORM entity with UUID identity, normalized unique email, display name, password hash, active state and timestamps.
- Alembic revision `0002_user_auth`, following clean root `0001`.
- Request-scoped SQLAlchemy session dependency.
- Argon2id password hashing through `argon2-cffi` high-level `PasswordHasher`.
- JWT bearer access tokens with server-locked HS256, issuer validation, expiration, issued-at and subject claims.
- Minimum 32-byte JWT secret and refusal to use the development default secret outside local/dev/test.
- `POST /api/v1/auth/register`.
- `POST /api/v1/auth/login`.
- Protected `GET /api/v1/auth/me`.
- Shared invalid-credentials response for missing users and wrong passwords.
- Inactive-account rejection.
- Password/password-hash fields are never serialized by the public user response.

## Security boundaries
- Passwords are never persisted in plaintext.
- JWT decode algorithms are configured server-side and cannot be selected by token content.
- Access tokens require `sub`, `iss`, `iat`, and `exp`.
- No Project/Site authorization exists yet; that arrives in later tasks.
- No refresh-token, password-reset, SSO, RBAC, or email-verification workflow is claimed by this foundation task.
- No Git commit.

## Acceptance
- Full backend regression suite passes.
- Migration head is exactly `0002`.
- Offline SQL creates only the `users` application table after the extension foundation.
- Register/login/me golden path passes in an isolated test database.
- Duplicate email, bad credentials, inactive account, invalid issuer, short JWT secret, non-HS256 algorithm and unsafe production default-secret cases are rejected.
- Live PostgreSQL Docker migration remains a local-runtime gate because the ChatGPT runtime has no Docker daemon.
