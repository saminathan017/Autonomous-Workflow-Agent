"""
Workflow engine - orchestrates task execution with retries and error handling.
"""
import time
import uuid
from datetime import datetime
from typing import List, Optional
from autonomous_workflow_agent.app.workflows.models import (
    WorkflowRun, WorkflowStatus, StepLog, StepStatus,
    EmailData, SheetRow
)
from autonomous_workflow_agent.app.workflows.state_store import get_state_store
from autonomous_workflow_agent.app.workflows.tasks.gmail_reader import get_gmail_reader
from autonomous_workflow_agent.app.workflows.tasks.sheets_writer import get_sheets_writer
from autonomous_workflow_agent.app.workflows.tasks.report_builder import get_report_builder
from autonomous_workflow_agent.app.workflows.analytics import get_analytics_store
from autonomous_workflow_agent.app.config import get_settings
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)


class WorkflowEngine:
    """Orchestrates workflow execution with deterministic steps."""
    
    def __init__(self):
        """Initialize the workflow engine."""
        self.settings = get_settings()
        self.state_store = get_state_store()
        self.analytics_store = get_analytics_store()
        self.gmail_reader = get_gmail_reader()
        self.sheets_writer = get_sheets_writer()
        self.report_builder = get_report_builder()
    
    def _execute_step_with_retry(
        self,
        run_id: str,
        step_name: str,
        step_func,
        *args,
        **kwargs
    ) -> tuple[bool, Optional[any], Optional[str]]:
        """
        Execute a step with retry logic.
        
        Args:
            run_id: Workflow run ID
            step_name: Name of the step
            step_func: Function to execute
            *args: Positional arguments for step_func
            **kwargs: Keyword arguments for step_func
            
        Returns:
            Tuple of (success, result, error_message)
        """
        max_retries = self.settings.workflow_max_retries
        retry_delay = self.settings.workflow_retry_delay_seconds
        
        for attempt in range(max_retries + 1):
            step_log = StepLog(
                step_name=step_name,
                status=StepStatus.RUNNING,
                started_at=datetime.now(),
                retry_count=attempt
            )
            
            try:
                logger.info(f"Executing step '{step_name}' (attempt {attempt + 1}/{max_retries + 1})")
                result = step_func(*args, **kwargs)
                
                step_log.status = StepStatus.COMPLETED
                step_log.completed_at = datetime.now()
                self.state_store.add_step_log(run_id, step_log)
                
                logger.info(f"Step '{step_name}' completed successfully")
                return True, result, None
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Step '{step_name}' failed (attempt {attempt + 1}): {error_msg}")
                
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    step_log.status = StepStatus.FAILED
                    step_log.completed_at = datetime.now()
                    step_log.error_message = error_msg
                    self.state_store.add_step_log(run_id, step_log)
                    
                    return False, None, error_msg
        
        return False, None, "Max retries exceeded"
    
    def execute_workflow(
        self,
        max_emails: int = 10,
        generate_report: bool = True
    ) -> WorkflowRun:
        """
        Execute the complete workflow.
        
        Args:
            max_emails: Maximum number of emails to process
            generate_report: Whether to generate AI report
            
        Returns:
            WorkflowRun object with execution results
        """
        # Create workflow run
        run_id = str(uuid.uuid4())
        run = WorkflowRun(
            run_id=run_id,
            status=WorkflowStatus.RUNNING,
            started_at=datetime.now()
        )
        
        self.state_store.create_run(run)
        logger.info(f"Started workflow run: {run_id}")
        
        try:
            # Step 1: Fetch emails from Gmail
            success, emails, error = self._execute_step_with_retry(
                run_id,
                "fetch_emails",
                self.gmail_reader.fetch_emails,
                max_results=max_emails
            )
            
            if not success or not emails:
                run.status = WorkflowStatus.FAILED
                run.error_message = error or "No emails fetched"
                run.completed_at = datetime.now()
                self.state_store.update_run(
                    run_id,
                    status=run.status,
                    error_message=run.error_message,
                    completed_at=run.completed_at
                )
                return run
            
            run.emails_processed = len(emails)
            logger.info(f"Fetched {len(emails)} emails")
            
            # Cache classifications for analytics
            for email in emails:
                if email.classification and email.sentiment:
                    try:
                        self.analytics_store.cache_classification(
                            email_id=email.message_id,
                            category=email.classification.category.value,
                            sentiment=email.sentiment.sentiment.value,
                            urgency_score=email.sentiment.urgency_score,
                            confidence=email.classification.confidence
                        )
                    except Exception as e:
                        logger.warning(f"Failed to cache classification: {e}")
            
            # Step 2: Write to Google Sheets
            sheet_rows = self._prepare_sheet_rows(emails)
            success, rows_written, error = self._execute_step_with_retry(
                run_id,
                "write_to_sheets",
                self.sheets_writer.write_rows,
                sheet_rows
            )
            
            if not success:
                logger.warning(f"Failed to write to sheets: {error}")
                # Don't fail the whole workflow, continue to report generation
            else:
                logger.info(f"Wrote {rows_written} rows to Google Sheets")
            
            # Step 3: Generate AI report (if requested)
            if generate_report:
                success, report_data, error = self._execute_step_with_retry(
                    run_id,
                    "generate_report",
                    self.report_builder.build_report,
                    emails
                )
                
                if success and report_data:
                    # Save report
                    report_path = self.report_builder.save_report(report_data)
                    run.report_path = str(report_path)
                    logger.info(f"Generated report: {report_path}")
                else:
                    logger.warning(f"Failed to generate report: {error}")
            
            # Workflow completed successfully
            run.status = WorkflowStatus.COMPLETED
            run.completed_at = datetime.now()
            self.state_store.update_run(
                run_id,
                status=run.status,
                completed_at=run.completed_at,
                emails_processed=run.emails_processed,
                report_path=run.report_path
            )
            
            logger.info(f"Workflow run {run_id} completed successfully")
            return run
            
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            run.status = WorkflowStatus.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.now()
            self.state_store.update_run(
                run_id,
                status=run.status,
                error_message=run.error_message,
                completed_at=run.completed_at
            )
            return run
    
    def _prepare_sheet_rows(self, emails: List[EmailData]) -> List[SheetRow]:
        """
        Prepare sheet rows from email data.
        
        Args:
            emails: List of EmailData objects
            
        Returns:
            List of SheetRow objects
        """
        rows = []
        for email in emails:
            # Extract classification and sentiment data
            category = "general"
            sentiment = "neutral"
            urgency_score = 0.0
            
            if email.classification:
                category = email.classification.category.value
            
            if email.sentiment:
                sentiment = email.sentiment.sentiment.value
                urgency_score = email.sentiment.urgency_score
            
            row = SheetRow(
                email_id=email.message_id,
                subject=email.subject,
                sender=email.sender,
                date=email.date.strftime("%Y-%m-%d %H:%M:%S"),
                summary=email.snippet[:200] if email.snippet else "",
                category=category,
                sentiment=sentiment,
                urgency_score=urgency_score,
                processed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            rows.append(row)
        return rows


def get_workflow_engine() -> WorkflowEngine:
    """Get a workflow engine instance."""
    return WorkflowEngine()
