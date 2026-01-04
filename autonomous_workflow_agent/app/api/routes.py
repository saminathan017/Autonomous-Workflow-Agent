"""
FastAPI routes for the Autonomous Workflow Agent.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from datetime import datetime
from autonomous_workflow_agent.app.workflows.models import (
    WorkflowTriggerRequest,
    WorkflowRunResponse,
    WorkflowRun,
    WorkflowStatus
)
from autonomous_workflow_agent.app.workflows.engine import get_workflow_engine
from autonomous_workflow_agent.app.workflows.state_store import get_state_store
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "autonomous_workflow_agent"}


@router.post("/run", response_model=WorkflowRunResponse)
async def trigger_workflow(
    request: WorkflowTriggerRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger a workflow execution.
    
    Args:
        request: Workflow trigger request
        background_tasks: FastAPI background tasks
        
    Returns:
        WorkflowRunResponse with run ID and status
    """
    try:
        logger.info(f"Triggering workflow: max_emails={request.max_emails}, generate_report={request.generate_report}")
        
        # Execute workflow in background
        engine = get_workflow_engine()
        
        # For now, execute synchronously (can be moved to background tasks)
        run = engine.execute_workflow(
            max_emails=request.max_emails,
            generate_report=request.generate_report
        )
        
        return WorkflowRunResponse(
            run_id=run.run_id,
            status=run.status,
            message=f"Workflow {'completed' if run.status == WorkflowStatus.COMPLETED else 'failed'}"
        )
        
    except Exception as e:
        logger.error(f"Error triggering workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs", response_model=List[WorkflowRun])
async def list_runs(
    limit: int = 50,
    status: Optional[WorkflowStatus] = None
):
    """
    List workflow runs.
    
    Args:
        limit: Maximum number of runs to return
        status: Optional status filter
        
    Returns:
        List of WorkflowRun objects
    """
    try:
        state_store = get_state_store()
        runs = state_store.list_runs(limit=limit, status=status)
        return runs
    except Exception as e:
        logger.error(f"Error listing runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}", response_model=WorkflowRun)
async def get_run(run_id: str):
    """
    Get a specific workflow run.
    
    Args:
        run_id: Run ID
        
    Returns:
        WorkflowRun object
    """
    try:
        state_store = get_state_store()
        run = state_store.get_run(run_id)
        
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        
        return run
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str):
    """
    Manually stop a workflow run.
    
    Args:
        run_id: Run ID
    """
    try:
        state_store = get_state_store()
        run = state_store.get_run(run_id)
        
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            
        # Update status to FAILED
        success = state_store.update_run(
            run_id, 
            status=WorkflowStatus.FAILED,
            error_message="Manually stopped by user",
            completed_at=datetime.utcnow()
        )
        
        if success:
            return {"status": "success", "message": f"Run {run_id} stopped"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update run status")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping run: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schedule")
async def schedule_workflow():
    """
    Schedule recurring workflow execution.
    
    Note: This is a placeholder for future implementation with APScheduler.
    """
    return {
        "message": "Scheduling not yet implemented",
        "status": "planned"
    }


# Analytics Endpoints

@router.get("/analytics/summary", tags=["analytics"])
async def get_analytics_summary(days: int = 7):
    """Get analytics summary for the last N days."""
    from autonomous_workflow_agent.app.workflows.analytics import get_analytics_store
    analytics = get_analytics_store()
    summary = analytics.get_summary(days=days)
    return summary


@router.get("/analytics/categories", tags=["analytics"])
async def get_category_distribution(days: int = 7):
    """Get email category distribution."""
    from autonomous_workflow_agent.app.workflows.analytics import get_analytics_store
    analytics = get_analytics_store()
    summary = analytics.get_summary(days=days)
    return {"categories": summary.get("categories", {})}




# Reports Endpoints

@router.get("/reports", tags=["reports"])
async def list_reports():
    """List all generated reports with urgency summaries."""
    from pathlib import Path
    import re
    from autonomous_workflow_agent.app.config import get_settings, get_project_root
    
    try:
        settings = get_settings()
        # Reports are in autonomous_workflow_agent/data/reports/
        reports_dir = get_project_root() / "data" / "reports"
        
        if not reports_dir.exists():
            return {"reports": []}
        
        reports = []
        for report_file in sorted(reports_dir.glob("report_*.md"), reverse=True):
            stats = {
                "filename": report_file.name,
                "path": str(report_file),
                "created_at": report_file.stat().st_mtime,
                "size": report_file.stat().st_size,
                "urgency_summary": None
            }
            
            # extract urgency stats from content
            try:
                content = report_file.read_text(encoding='utf-8')
                
                # Look for Urgency Breakdown section
                important_match = re.search(r'- \*\*Important:\*\* (\d+)', content)
                review_match = re.search(r'- \*\*Needed Review:\*\* (\d+)', content)
                
                if important_match or review_match:
                    important_count = int(important_match.group(1)) if important_match else 0
                    review_count = int(review_match.group(1)) if review_match else 0
                    
                    if important_count > 0:
                        label = "Important"
                        color = "red"
                    elif review_count > 0:
                        label = "Review Needed"
                        color = "orange"
                    else:
                        label = "Routine"
                        color = "green"
                        
                    stats["urgency_summary"] = {
                        "label": label,
                        "color": color,
                        "important": important_count,
                        "review": review_count
                    }
            except Exception as e:
                logger.warning(f"Error parsing report {report_file.name}: {e}")
                
            reports.append(stats)
        
        return {"reports": reports}
    except Exception as e:
        logger.error(f"Error listing reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{filename}", tags=["reports"])
async def get_report(filename: str):
    """Get the content of a specific report."""
    from pathlib import Path
    from autonomous_workflow_agent.app.config import get_project_root
    
    try:
        # Security: ensure filename doesn't contain path traversal
        if ".." in filename or "/" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        reports_dir = get_project_root() / "data" / "reports"
        report_file = reports_dir / filename
        
        if not report_file.exists():
            raise HTTPException(status_code=404, detail="Report not found")
        
        content = report_file.read_text()
        
        return {
            "filename": filename,
            "content": content,
            "created_at": report_file.stat().st_mtime,
            "size": report_file.stat().st_size
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Gmail Push API Endpoints

@router.post("/webhooks/gmail", tags=["webhooks"])
async def gmail_webhook(request: dict):
    """Gmail Push API webhook endpoint."""
    from autonomous_workflow_agent.app.auth.gmail_push import get_gmail_push_manager
    try:
        push_manager = get_gmail_push_manager()
        history_id = push_manager.process_notification(request)
        
        if history_id:
            logger.info(f"Gmail notification received, history ID: {history_id}")
            return {"status": "success", "history_id": history_id}
        else:
            return {"status": "ignored"}
    except Exception as e:
        logger.error(f"Error processing Gmail webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gmail/watch", tags=["gmail"])
async def enable_gmail_watch(topic_name: str):
    """Enable Gmail push notifications."""
    from autonomous_workflow_agent.app.auth.gmail_push import get_gmail_push_manager
    try:
        push_manager = get_gmail_push_manager()
        result = push_manager.setup_watch(topic_name)
        return {"status": "success", "watch_response": result}
    except Exception as e:
        logger.error(f"Error enabling Gmail watch: {e}")
        raise HTTPException(status_code=500, detail=str(e))

