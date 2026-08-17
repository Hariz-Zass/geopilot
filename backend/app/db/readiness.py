from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.core.config import get_settings

REQUIRED_EXTENSIONS = frozenset({"postgis", "vector"})
READINESS_SQL = """
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    current_setting('server_version_num')::integer AS server_version_num,
    current_setting('server_version') AS server_version,
    ext.extname,
    ext.extversion
FROM pg_extension AS ext
WHERE ext.extname IN ('postgis', 'vector')
ORDER BY ext.extname;
"""


@dataclass(frozen=True, slots=True)
class DatabaseReadiness:
    ready: bool
    database_name: str | None
    database_user: str | None
    postgres_version: str | None
    postgres_version_num: int | None
    extensions: Mapping[str, str]
    missing_extensions: tuple[str, ...]
    error: str | None = None

    def public_payload(self) -> dict[str, Any]:
        """Return non-secret readiness metadata safe for the local system endpoint."""
        return {
            "status": "ready" if self.ready else "not_ready",
            "database": self.database_name,
            "postgres_version": self.postgres_version,
            "extensions": dict(sorted(self.extensions.items())),
            "missing_extensions": list(self.missing_extensions),
            "error": self.error,
        }


def _evaluate_rows(rows: list[Mapping[str, Any]]) -> DatabaseReadiness:
    if not rows:
        return DatabaseReadiness(
            ready=False,
            database_name=None,
            database_user=None,
            postgres_version=None,
            postgres_version_num=None,
            extensions={},
            missing_extensions=tuple(sorted(REQUIRED_EXTENSIONS)),
            error="database capability query returned no extension rows",
        )

    first = rows[0]
    extensions = {
        str(row["extname"]): str(row["extversion"])
        for row in rows
        if row.get("extname") is not None
    }
    missing = tuple(sorted(REQUIRED_EXTENSIONS.difference(extensions)))
    version_num = int(first["server_version_num"])

    # GeoPilot clean-room runtime is intentionally based on PostgreSQL 16+.
    postgres_supported = version_num >= 160000
    error: str | None = None
    if missing:
        error = f"missing required database extensions: {', '.join(missing)}"
    elif not postgres_supported:
        error = "PostgreSQL 16 or newer is required"

    return DatabaseReadiness(
        ready=not missing and postgres_supported,
        database_name=str(first["database_name"]),
        database_user=str(first["database_user"]),
        postgres_version=str(first["server_version"]),
        postgres_version_num=version_num,
        extensions=extensions,
        missing_extensions=missing,
        error=error,
    )


def verify_database_readiness() -> DatabaseReadiness:
    """Connect to PostgreSQL and verify the minimum GeoPilot database capabilities.

    The driver import is intentionally local so static tooling can inspect the module
    without requiring a live database or importing the DB driver during collection.
    """

    settings = get_settings()
    try:
        import psycopg
        from psycopg.rows import dict_row

        # psycopg accepts postgresql://, while application SQLAlchemy URLs may contain
        # the explicit +psycopg dialect marker.
        dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(
            dsn,
            connect_timeout=settings.db_connect_timeout_seconds,
            row_factory=dict_row,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(READINESS_SQL)
                rows = list(cursor.fetchall())
        return _evaluate_rows(rows)
    except Exception as exc:  # readiness must fail closed for any connection/capability error
        return DatabaseReadiness(
            ready=False,
            database_name=None,
            database_user=None,
            postgres_version=None,
            postgres_version_num=None,
            extensions={},
            missing_extensions=tuple(sorted(REQUIRED_EXTENSIONS)),
            error=f"database readiness check failed: {type(exc).__name__}",
        )
