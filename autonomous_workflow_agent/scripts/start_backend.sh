#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Autonomous Workflow Agent — backend launcher
# Called by Start_App.command (root) or directly from the project directory.
# Supports native macOS (brew PostgreSQL + Redis) and Docker Compose.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
PYTHONPATH="$REPO_ROOT"
export PYTHONPATH

# ── Find Python ───────────────────────────────────────────────────────────────
PYTHON=""
for candidate in \
  "/opt/homebrew/Caskroom/miniconda/base/bin/python" \
  "$HOME/miniconda3/bin/python" \
  "$HOME/anaconda3/bin/python" \
  "$HOME/miniforge3/bin/python" \
  "$ROOT_DIR/venv/bin/python" \
  "$(which python3 2>/dev/null || true)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "ERROR: Python not found."
  echo "Install miniconda: https://docs.conda.io/en/latest/miniconda.html"
  exit 1
fi
echo "Python  : $PYTHON ($("$PYTHON" --version 2>&1))"

# ── PostgreSQL ────────────────────────────────────────────────────────────────
if ! pg_isready -q 2>/dev/null; then
  echo "PostgreSQL not running — attempting to start via brew..."
  brew services start postgresql@16 2>/dev/null \
    || brew services start postgresql 2>/dev/null \
    || true
  for i in $(seq 1 20); do
    pg_isready -q 2>/dev/null && break
    printf "  waiting for PostgreSQL... (%s/20)\r" "$i"
    sleep 1
  done
  echo ""
fi
pg_isready || { echo "ERROR: PostgreSQL is not accepting connections."; exit 1; }
echo "Postgres: ready"

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_CLI=$(command -v redis-cli 2>/dev/null || echo "/opt/homebrew/bin/redis-cli")
if ! "$REDIS_CLI" ping &>/dev/null; then
  echo "Redis not running — attempting to start via brew..."
  brew services start redis 2>/dev/null || true
  for i in $(seq 1 10); do
    "$REDIS_CLI" ping &>/dev/null && break
    printf "  waiting for Redis... (%s/10)\r" "$i"
    sleep 1
  done
  echo ""
fi
"$REDIS_CLI" ping || { echo "ERROR: Redis is not responding."; exit 1; }
echo "Redis   : ready"

# ── Initialise / verify database tables ───────────────────────────────────────
cd "$ROOT_DIR"
echo "DB init : running..."
"$PYTHON" scripts/init_db.py || {
  echo ""
  echo "ERROR: Database initialisation failed."
  echo "Check DATABASE_URL in autonomous_workflow_agent/.env"
  exit 1
}

# ── Launch server ─────────────────────────────────────────────────────────────
# --workers 2: two processes share work; Redis pub/sub keeps WebSocket events
#   cross-process. PostgreSQL advisory lock ensures only one worker runs the
#   APScheduler. Increase workers only on a dedicated server, not a laptop.
echo ""
echo "Starting server on http://127.0.0.1:8001 (workers=2) ..."
echo "Press Ctrl-C to stop."
echo ""
"$PYTHON" -m uvicorn \
  autonomous_workflow_agent.app.main:app \
  --host 127.0.0.1 \
  --port 8001 \
  --workers 2 \
  --log-level info
