#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Autonomous Workflow Agent — macOS launcher
# Double-click this file in Finder to start the full stack and open the UI.
#
# What this script does:
#   1. Locates your Python (miniconda > venv > system)
#   2. Starts PostgreSQL via brew services if not already running
#   3. Starts Redis via brew services if not already running
#   4. Initialises database tables (safe to run repeatedly)
#   5. Kills any stale server on port 8001
#   6. Launches uvicorn with 2 workers (multi-process, Redis-backed WebSockets)
#   7. Opens http://127.0.0.1:8001 in your browser after 4 seconds
#
# Prerequisites:
#   brew install postgresql redis
#   pip install -r autonomous_workflow_agent/requirements.txt
#   Copy .env.example → .env and fill in your API keys
#   Run authenticate.py once to authorise Gmail / Sheets
# ──────────────────────────────────────────────────────────────────────────────

# cd to the directory this file lives in so relative paths always work
cd "$(dirname "$0")"

ROOT_DIR="$(pwd)"
PROJECT_DIR="$ROOT_DIR/autonomous_workflow_agent"
export PYTHONPATH="$ROOT_DIR"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${RESET}"; }
warn() { echo -e "${YELLOW}⚠ $*${RESET}"; }
fail() { echo -e "${RED}✗ $*${RESET}"; exit 1; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Autonomous Workflow Agent"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Find Python ─────────────────────────────────────────────────────────────
PYTHON=""
for candidate in \
  "/opt/homebrew/Caskroom/miniconda/base/bin/python" \
  "$HOME/miniconda3/bin/python" \
  "$HOME/anaconda3/bin/python" \
  "$HOME/miniforge3/bin/python" \
  "$PROJECT_DIR/venv/bin/python" \
  "$(command -v python3 2>/dev/null || true)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then
    PYTHON="$candidate"
    break
  fi
done
[ -z "$PYTHON" ] && fail "Python not found. Install miniconda: https://docs.conda.io/en/latest/miniconda.html"
ok "Python  : $PYTHON ($("$PYTHON" --version 2>&1))"

# ── 2. PostgreSQL ──────────────────────────────────────────────────────────────
if ! pg_isready -q 2>/dev/null; then
  warn "PostgreSQL not running — starting via brew..."
  brew services start postgresql@16 2>/dev/null \
    || brew services start postgresql 2>/dev/null \
    || warn "brew services start failed — trying anyway"
  for i in $(seq 1 20); do
    pg_isready -q 2>/dev/null && break
    sleep 1
  done
fi
pg_isready -q || fail "PostgreSQL is not accepting connections. Run: brew install postgresql && brew services start postgresql"
ok "Postgres: ready"

# ── 3. Redis ───────────────────────────────────────────────────────────────────
REDIS_CLI=$(command -v redis-cli 2>/dev/null || echo "/opt/homebrew/bin/redis-cli")
if ! "$REDIS_CLI" ping &>/dev/null 2>&1; then
  warn "Redis not running — starting via brew..."
  brew services start redis 2>/dev/null \
    || warn "brew services start redis failed — trying anyway"
  for i in $(seq 1 10); do
    "$REDIS_CLI" ping &>/dev/null 2>&1 && break
    sleep 1
  done
fi
"$REDIS_CLI" ping &>/dev/null || fail "Redis is not responding. Run: brew install redis && brew services start redis"
ok "Redis   : ready"

# ── 4. Initialise database ─────────────────────────────────────────────────────
echo ""
echo "Initialising database tables..."
"$PYTHON" "$PROJECT_DIR/scripts/init_db.py" \
  || fail "Database init failed. Check DATABASE_URL in autonomous_workflow_agent/.env"
ok "Database: tables verified"

# ── 5. Kill any previous server on port 8001 ──────────────────────────────────
lsof -ti:8001 | xargs kill -9 2>/dev/null && warn "Killed stale server on port 8001" || true
sleep 0.5

# ── 6. Open browser after 4 seconds ───────────────────────────────────────────
(sleep 4 && open "http://127.0.0.1:8001") &

# ── 7. Launch server ───────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Starting server → http://127.0.0.1:8001"
echo "   Workers: 2  |  Event bus: Redis  |  DB: PostgreSQL"
echo "   Press Ctrl-C to stop"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

"$PYTHON" -m uvicorn \
  autonomous_workflow_agent.app.main:app \
  --host 127.0.0.1 \
  --port 8001 \
  --workers 2 \
  --log-level info
