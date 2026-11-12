#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example to .env and set MEDIA_API_TOKEN" >&2
  exit 1
fi
set -a; source .env; set +a
exec python3 -m uvicorn app.main:app \
  --host "${MEDIA_API_HOST:-0.0.0.0}" \
  --port "${MEDIA_API_PORT:-8787}" \
  --workers "${MEDIA_API_WORKERS:-1}"
