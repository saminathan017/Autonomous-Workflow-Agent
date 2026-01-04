#!/usr/bin/env python3
"""
Database initialization script.
Creates the SQLite database and schema.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from autonomous_workflow_agent.app.workflows.state_store import StateStore
from autonomous_workflow_agent.app.config import get_settings, get_project_root
from autonomous_workflow_agent.app.utils.logging import setup_logging, get_logger

# Setup logging
setup_logging(log_level="INFO")
logger = get_logger(__name__)


def main():
    """Initialize the database."""
    logger.info("Initializing database...")
    
    settings = get_settings()
    db_path = get_project_root() / settings.database_path
    
    logger.info(f"Database path: {db_path}")
    
    # Create state store (this will initialize the database)
    state_store = StateStore(db_path=db_path)
    
    logger.info("✓ Database initialized successfully!")
    logger.info(f"  Location: {db_path}")
    logger.info(f"  Tables: workflow_runs, step_logs")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
