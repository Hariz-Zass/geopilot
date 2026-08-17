#!/usr/bin/env sh
set -eu

printf 'Backend health: '
curl -fsS http://localhost:${APP_PORT:-8000}/health
printf '\nFrontend: '
curl -fsSI http://localhost:${FRONTEND_PORT:-5173} | head -n 1
printf 'Database extensions:\n'
docker compose exec -T db psql -U "${POSTGRES_USER:-geopilot}" -d "${POSTGRES_DB:-geopilot}" -Atc \
  "SELECT extname FROM pg_extension WHERE extname IN ('postgis','vector') ORDER BY extname;"
