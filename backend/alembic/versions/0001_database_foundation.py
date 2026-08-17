"""database foundation

Revision ID: 0001
Revises: None
Create Date: 2026-08-14
"""

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Extensions are infrastructure prerequisites and are also initialized by the
    # local DB image. Keeping idempotent CREATE EXTENSION here makes a fresh
    # migration target self-describing and safe to apply more than once.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Intentionally do not DROP shared database capabilities. A schema downgrade
    # must never remove PostGIS/pgvector and risk destroying unrelated spatial or
    # vector data. Revision rollback only relinquishes Alembic ownership state.
    pass
