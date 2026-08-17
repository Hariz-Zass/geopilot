#!/usr/bin/env sh
set -eu

POSTGRES_USER="${POSTGRES_USER:-geopilot}"
POSTGRES_DB="${POSTGRES_DB:-geopilot}"

printf 'GeoPilot database capability audit\n'
printf '%s\n' '---------------------------------'

docker compose exec -T db psql \
  -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -P pager=off \
  -c "SELECT current_database() AS database, current_user AS role, version();" \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('postgis','vector') ORDER BY extname;" \
  -c "SELECT PostGIS_Full_Version();" \
  -c "SELECT '[1,2,3]'::vector(3) AS vector_smoke_test;"

printf '\nBackend readiness endpoint:\n'
curl -fsS "http://localhost:${APP_PORT:-8000}/ready"
printf '\n'
