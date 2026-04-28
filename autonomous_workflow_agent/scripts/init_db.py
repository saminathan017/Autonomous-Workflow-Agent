#!/usr/bin/env python3
"""Database initialisation — safe to run multiple times (idempotent).

Usage:
    cd autonomous_workflow_agent
    python scripts/init_db.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from autonomous_workflow_agent.app.config import get_settings
from autonomous_workflow_agent.app.utils.logging import configure_logging
from autonomous_workflow_agent.app.workflows.state_store import StateStore

configure_logging("INFO")


async def main() -> int:
    settings = get_settings()
    print(f"Connecting to PostgreSQL: {settings.database_url!r} ...")
    store = StateStore()
    try:
        await store.initialize()
        print("PostgreSQL ready — all tables created/verified.")
        print(
            "Tables: workflow_runs, step_logs, analytics, email_classifications, "
            "processed_emails, draft_replies, action_items, schedule_config, "
            "user_settings, follow_ups, email_translations, briefing_cache"
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        print(
            "\nMake sure PostgreSQL is running and DATABASE_URL in .env is correct.\n"
            "Quick setup:\n"
            "  brew install postgresql@16\n"
            "  brew services start postgresql@16\n"
            "  createdb workflow_agent\n"
        )
        return 1
    finally:
        await store.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
