#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  trap - INT TERM EXIT
  if [[ -n "$FRONTEND_PID" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
  if [[ -n "$BACKEND_PID" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
}
trap cleanup INT TERM EXIT

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is required. On macOS: brew install cloudflared" >&2
  exit 1
fi

if [[ ! -x "$BACKEND_DIR/.venv/bin/uvicorn" ]]; then
  echo "backend/.venv is missing. Create it and install backend/requirements.txt first." >&2
  exit 1
fi

if curl --fail --silent http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "Reusing FastAPI already running on http://127.0.0.1:8000"
else
  echo "Starting FastAPI on http://127.0.0.1:8000"
  (
    cd "$BACKEND_DIR"
    exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
  ) &
  BACKEND_PID=$!
fi

if curl --fail --silent http://127.0.0.1:5173/ >/dev/null 2>&1; then
  echo "Reusing Vite already running on http://127.0.0.1:5173"
else
  echo "Starting Vite on http://127.0.0.1:5173"
  (
    cd "$FRONTEND_DIR"
    exec npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
  ) &
  FRONTEND_PID=$!
fi

for _ in {1..40}; do
  if curl --fail --silent http://127.0.0.1:8000/health >/dev/null \
    && curl --fail --silent http://127.0.0.1:5173/ >/dev/null; then
    break
  fi
  if [[ -n "$BACKEND_PID" ]] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "The backend stopped before the tunnel could start." >&2
    exit 1
  fi
  if [[ -n "$FRONTEND_PID" ]] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "A local server stopped before the tunnel could start." >&2
    exit 1
  fi
  sleep 0.25
done

if ! curl --fail --silent http://127.0.0.1:8000/health >/dev/null \
  || ! curl --fail --silent http://127.0.0.1:5173/ >/dev/null; then
  echo "Timed out waiting for the local servers." >&2
  exit 1
fi

echo
echo "Cloudflare will print one https://*.trycloudflare.com URL below."
echo "Share that URL with your teammates. Press Ctrl+C to stop everything."
echo

# The public request keeps its random trycloudflare.com host. Rewrite only
# the origin Host header so Vite accepts it without opening allowedHosts to
# every possible domain. Cloudflare still terminates public HTTPS.
cloudflared tunnel \
  --no-autoupdate \
  --url http://127.0.0.1:5173 \
  --http-host-header 127.0.0.1:5173
