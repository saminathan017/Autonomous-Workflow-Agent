#!/usr/bin/env python3
"""
Manual workflow execution script.
Useful for testing and debugging.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from autonomous_workflow_agent.app.workflows.engine import get_workflow_engine
from autonomous_workflow_agent.app.utils.logging import setup_logging, get_logger

# Setup logging
setup_logging(log_level="INFO")
logger = get_logger(__name__)


def main():
    """Run a single workflow execution."""
    logger.info("=" * 60)
    logger.info("Manual Workflow Execution")
    logger.info("=" * 60)
    
    # Get workflow engine
    engine = get_workflow_engine()
    
    # Execute workflow
    logger.info("Starting workflow execution...")
    run = engine.execute_workflow(
        max_emails=10,
        generate_report=True
    )
    
    # Print results
    logger.info("=" * 60)
    logger.info("Workflow Execution Complete")
    logger.info("=" * 60)
    logger.info(f"Run ID: {run.run_id}")
    logger.info(f"Status: {run.status.value}")
    logger.info(f"Emails Processed: {run.emails_processed}")
    
    if run.report_path:
        logger.info(f"Report: {run.report_path}")
    
    if run.error_message:
        logger.error(f"Error: {run.error_message}")
    
    logger.info("=" * 60)
    
    # Print step details
    logger.info("Step Execution Details:")
    for step in run.steps:
        status_icon = "✓" if step.status.value == "completed" else "✗"
        logger.info(f"  {status_icon} {step.step_name}: {step.status.value}")
        if step.error_message:
            logger.error(f"    Error: {step.error_message}")
    
    return 0 if run.status.value == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
