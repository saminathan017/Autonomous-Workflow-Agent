#!/usr/bin/env python3
"""
Google OAuth authentication helper.
Run once before starting the server to generate token.json.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from autonomous_workflow_agent.app.auth.google_oauth import get_auth_manager
from autonomous_workflow_agent.app.utils.logging import configure_logging

configure_logging("INFO")


def main() -> int:
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Google OAuth Authentication")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print("Your browser will open to authenticate with Google.")
    print("Grant both Gmail (read-only) and Sheets permissions.")
    print()

    auth = get_auth_manager()
    if auth.authenticate():
        print()
        print("✓ Authentication successful!")
        print(f"✓ Token saved → {auth.token_path}")
        print()
        print("You can now start the server:")
        print("  Double-click Start_App.command")
        print("  — or —")
        print("  cd autonomous_workflow_agent")
        print("  uvicorn autonomous_workflow_agent.app.main:app --host 0.0.0.0 --port 8001")
        return 0

    print()
    print("✗ Authentication failed. Check:")
    print("  1. credentials.json exists in autonomous_workflow_agent/")
    print("  2. Gmail API and Sheets API are enabled in Google Cloud Console")
    print("  3. OAuth consent screen is configured")
    return 1


if __name__ == "__main__":
    sys.exit(main())
