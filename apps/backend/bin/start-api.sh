#!/bin/sh
set -eu

# The free demo has no pre-deploy phase. Apply its pending migrations before
# accepting requests, using the explicit direct connection instead of a fallback.
if [ "${ENV:-dev}" = "demo" ]; then
  : "${DATABASE_URL_DIRECT:?Set DATABASE_URL_DIRECT to the demo database}"
  if [ -n "${DATABASE_URL_GOLDEN_DIRECT:-}" ]; then
    # The pristine parent branch must carry the current schema and the seed:
    # every nightly reset copies it over the demo branch (ADR-052).
    FLRC_MIGRATIONS_URL="$DATABASE_URL_GOLDEN_DIRECT" alembic upgrade head
    DATABASE_URL_DIRECT="$DATABASE_URL_GOLDEN_DIRECT" flrc seed --demo
    FLRC_MIGRATIONS_URL="$DATABASE_URL_DIRECT" alembic upgrade head
  else
    FLRC_MIGRATIONS_URL="$DATABASE_URL_DIRECT" alembic upgrade head
    flrc seed --demo
  fi
fi

exec uvicorn flrc.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips='*' --no-access-log
