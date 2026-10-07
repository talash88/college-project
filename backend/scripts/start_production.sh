#!/bin/sh
# Step 17: production container entrypoint — wait for Postgres, migrate once, start API.
# Single migration runner: for a one-instance college deployment this container
# performs `alembic upgrade head` before exec'ing uvicorn. For multi-replica
# setups, run migrations as a separate one-shot job instead (see deployment doc).
set -eu

# Derive the pg_isready probe from DATABASE_URL so there is exactly one source
# of truth for the database location (DB_* overrides only for exotic setups).
PROBE="$(DB_HOST="${DB_HOST:-}" DB_PORT="${DB_PORT:-}" DB_USER="${DB_USER:-}" DB_NAME="${DB_NAME:-}" \
  DATABASE_URL="${DATABASE_URL:-}" python - <<'EOF'
import os
from urllib.parse import urlparse
url = os.environ.get("DATABASE_URL", "")
p = urlparse(url.replace("+asyncpg", "").replace("+psycopg2", ""))
print(" ".join([
    os.environ.get("DB_HOST") or p.hostname or "postgres",
    str(os.environ.get("DB_PORT") or p.port or 5432),
    os.environ.get("DB_USER") or p.username or "campusxolve",
    os.environ.get("DB_NAME") or (p.path or "/campusxolve").lstrip("/"),
]))
EOF
)"
set -- $PROBE
HOST="$1"; PORT="$2"; USER="$3"; DB="$4"

echo "[start] waiting for postgres at ${HOST}:${PORT} ..."
ATTEMPTS=0
until pg_isready -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" >/dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [ "$ATTEMPTS" -ge 60 ]; then
    echo "[start] ERROR: postgres not reachable after 60s" >&2
    exit 1
  fi
  sleep 2
done
echo "[start] postgres reachable; running migrations ..."
python -m alembic upgrade head

echo "[start] launching uvicorn (ENVIRONMENT=${ENVIRONMENT:-production}) ..."
exec python -m uvicorn app.main:app \
  --host "${API_HOST:-0.0.0.0}" \
  --port "${API_PORT:-8000}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
