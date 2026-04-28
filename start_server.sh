#!/usr/bin/env bash
# Autonomous Workflow Agent — CLI launcher
# For macOS users: double-click Start_App.command instead.
# This script delegates to autonomous_workflow_agent/scripts/start_backend.sh
# which handles service checks, DB init, and uvicorn startup.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT_DIR"

# Open browser after 4 seconds (macOS only; silently skipped on Linux)
(sleep 4 && open "http://127.0.0.1:8001" 2>/dev/null) &

cd "$ROOT_DIR/autonomous_workflow_agent"
exec ./scripts/start_backend.sh
