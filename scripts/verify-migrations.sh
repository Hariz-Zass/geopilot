#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../backend"

echo "[migration] current heads"
alembic heads

echo "[migration] history"
alembic history --verbose

echo "[migration] offline upgrade SQL"
alembic upgrade head --sql >/tmp/geopilot-alembic-upgrade.sql
grep -F "CREATE EXTENSION IF NOT EXISTS postgis" /tmp/geopilot-alembic-upgrade.sql >/dev/null
grep -F "CREATE EXTENSION IF NOT EXISTS vector" /tmp/geopilot-alembic-upgrade.sql >/dev/null

echo "[migration] PASS"
