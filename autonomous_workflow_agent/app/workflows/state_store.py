"""
SQLite state store for workflow persistence.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from autonomous_workflow_agent.app.config import get_settings, get_project_root
from autonomous_workflow_agent.app.workflows.models import WorkflowRun, WorkflowStatus, StepLog, StepStatus
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)


class StateStore:
    """SQLite-based state persistence for workflows."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the state store.
        
        Args:
            db_path: Path to SQLite database file
        """
        if db_path is None:
            settings = get_settings()
            db_path = settings.get_absolute_database_path()
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Initialize database schema if not exists."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Workflow runs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_message TEXT,
                    emails_processed INTEGER DEFAULT 0,
                    report_path TEXT
                )
            """)
            
            # Step logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS step_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    metadata TEXT,
                    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id)
                )
            """)
            
            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_status 
                ON workflow_runs(status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_started 
                ON workflow_runs(started_at DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_steps_run_id 
                ON step_logs(run_id)
            """)
            
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
            
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
        finally:
            conn.close()
    
    def create_run(self, run: WorkflowRun) -> bool:
        """
        Create a new workflow run.
        
        Args:
            run: WorkflowRun object
            
        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO workflow_runs 
                (run_id, status, started_at, completed_at, error_message, 
                 emails_processed, report_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                run.run_id,
                run.status.value,
                run.started_at.isoformat(),
                run.completed_at.isoformat() if run.completed_at else None,
                run.error_message,
                run.emails_processed,
                run.report_path
            ))
            conn.commit()
            logger.info(f"Created workflow run: {run.run_id}")
            return True
        except Exception as e:
            logger.error(f"Error creating run: {e}")
            return False
        finally:
            conn.close()
    
    def update_run(self, run_id: str, **kwargs) -> bool:
        """
        Update a workflow run.
        
        Args:
            run_id: Run ID
            **kwargs: Fields to update
            
        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        try:
            # Build update query
            fields = []
            values = []
            for key, value in kwargs.items():
                if key == 'status' and isinstance(value, WorkflowStatus):
                    value = value.value
                elif key in ['started_at', 'completed_at'] and isinstance(value, datetime):
                    value = value.isoformat()
                fields.append(f"{key} = ?")
                values.append(value)
            
            values.append(run_id)
            query = f"UPDATE workflow_runs SET {', '.join(fields)} WHERE run_id = ?"
            
            cursor = conn.cursor()
            cursor.execute(query, values)
            conn.commit()
            logger.info(f"Updated workflow run: {run_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating run: {e}")
            return False
        finally:
            conn.close()
    
    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        """
        Get a workflow run by ID.
        
        Args:
            run_id: Run ID
            
        Returns:
            WorkflowRun object or None
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM workflow_runs WHERE run_id = ?
            """, (run_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Get step logs
            cursor.execute("""
                SELECT * FROM step_logs WHERE run_id = ? ORDER BY id
            """, (run_id,))
            step_rows = cursor.fetchall()
            
            steps = []
            for step_row in step_rows:
                steps.append(StepLog(
                    step_name=step_row['step_name'],
                    status=StepStatus(step_row['status']),
                    started_at=datetime.fromisoformat(step_row['started_at']) if step_row['started_at'] else None,
                    completed_at=datetime.fromisoformat(step_row['completed_at']) if step_row['completed_at'] else None,
                    error_message=step_row['error_message'],
                    retry_count=step_row['retry_count'],
                    metadata=json.loads(step_row['metadata']) if step_row['metadata'] else {}
                ))
            
            return WorkflowRun(
                run_id=row['run_id'],
                status=WorkflowStatus(row['status']),
                started_at=datetime.fromisoformat(row['started_at']),
                completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                error_message=row['error_message'],
                steps=steps,
                emails_processed=row['emails_processed'],
                report_path=row['report_path']
            )
        except Exception as e:
            logger.error(f"Error getting run: {e}")
            return None
        finally:
            conn.close()
    
    def list_runs(self, limit: int = 50, status: Optional[WorkflowStatus] = None) -> List[WorkflowRun]:
        """
        List workflow runs.
        
        Args:
            limit: Maximum number of runs to return
            status: Optional status filter
            
        Returns:
            List of WorkflowRun objects
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            if status:
                cursor.execute("""
                    SELECT run_id FROM workflow_runs 
                    WHERE status = ?
                    ORDER BY started_at DESC 
                    LIMIT ?
                """, (status.value, limit))
            else:
                cursor.execute("""
                    SELECT run_id FROM workflow_runs 
                    ORDER BY started_at DESC 
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            runs = []
            for row in rows:
                run = self.get_run(row['run_id'])
                if run:
                    runs.append(run)
            
            return runs
        except Exception as e:
            logger.error(f"Error listing runs: {e}")
            return []
        finally:
            conn.close()
    
    def add_step_log(self, run_id: str, step: StepLog) -> bool:
        """
        Add a step log entry.
        
        Args:
            run_id: Run ID
            step: StepLog object
            
        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO step_logs 
                (run_id, step_name, status, started_at, completed_at, 
                 error_message, retry_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                step.step_name,
                step.status.value,
                step.started_at.isoformat() if step.started_at else None,
                step.completed_at.isoformat() if step.completed_at else None,
                step.error_message,
                step.retry_count,
                json.dumps(step.metadata) if step.metadata else None
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding step log: {e}")
            return False
        finally:
            conn.close()


# Global state store instance
_state_store: Optional[StateStore] = None


def get_state_store() -> StateStore:
    """Get or create the global state store instance."""
    global _state_store
    if _state_store is None:
        _state_store = StateStore()
    return _state_store
