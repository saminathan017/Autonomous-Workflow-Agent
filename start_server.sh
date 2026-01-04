#!/bin/bash
# Start the Autonomous Workflow Agent server on localhost:8000

# Kill any existing server on port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# Open the browser after a brief delay
(sleep 2 && open "http://127.0.0.1:8000") &

# Start the server
cd "$(dirname "$0")"
python -m uvicorn autonomous_workflow_agent.app.main:app --reload --host 127.0.0.1 --port 8000
