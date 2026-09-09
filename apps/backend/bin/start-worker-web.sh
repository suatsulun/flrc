#!/usr/bin/env bash
set -euo pipefail

uv run uvicorn flrc.workers.health:app --host 0.0.0.0 --port "${PORT:-10000}" &
HEALTH_PID=$!

uv run celery -A flrc.workers.celery:celery_app worker \
  --loglevel=INFO \
  --pool=solo \
  --concurrency=1 \
  --without-gossip \
  --without-mingle \
  --without-heartbeat &
CELERY_PID=$!

cleanup() {
  kill "$HEALTH_PID" "$CELERY_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait -n "$HEALTH_PID" "$CELERY_PID"
status=$?
cleanup
wait || true
exit "$status"
