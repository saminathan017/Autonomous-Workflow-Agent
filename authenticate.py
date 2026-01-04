#!/usr/bin/env python
"""
OAuth Authentication Helper Script

Run this script to authenticate with Google and generate token.json.
This must be done before running workflows that access Gmail or Google Sheets.
"""
import sys
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from autonomous_workflow_agent.app.auth.google_oauth import get_auth_manager
from autonomous_workflow_agent.app.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

def main():
    """Run OAuth authentication flow."""
    print("=" * 60)
    print("Google OAuth Authentication")
    print("=" * 60)
    print()
    print("This will open your browser to authenticate with Google.")
    print("Please sign in and grant the requested permissions.")
    print()
    
    auth_manager = get_auth_manager()
    
    if auth_manager.authenticate():
        print()
        print("✓ Authentication successful!")
        print(f"✓ Token saved to: {auth_manager.token_path}")
        print()
        print("You can now run workflows that access Gmail and Google Sheets.")
        return 0
    else:
        print()
        print("✗ Authentication failed!")
        print()
        print("Please check:")
        print("1. credentials.json exists in the project root")
        print("2. Your Google Cloud project is properly configured")
        print("3. Gmail and Sheets APIs are enabled")
        return 1

if __name__ == "__main__":
    sys.exit(main())
