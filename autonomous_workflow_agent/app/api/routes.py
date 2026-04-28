from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from loguru import logger

from autonomous_workflow_agent.app.config import get_project_root
from autonomous_workflow_agent.app.workflows.engine import get_workflow_engine
from autonomous_workflow_agent.app.workflows.event_bus import subscribe_events
from autonomous_workflow_agent.app.workflows.models import (
    ActionItem,
    ComposeRequest,
    DraftReply,
    FollowUp,
    ScheduleConfig,
    UserSettings,
    WorkflowRun,
    WorkflowRunResponse,
    WorkflowStatus,
    WorkflowTriggerRequest,
)
from autonomous_workflow_agent.app.workflows.state_store import get_state_store

router = APIRouter()


# ── health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check() -> dict[str, str]:
    store = get_state_store()
    from autonomous_workflow_agent.app.workflows.event_bus import ping_redis

    db_ok = await store.ping()
    redis_ok = await ping_redis()
    status = "healthy" if db_ok and redis_ok else "degraded"
    return {
        "status": status,
        "service": "autonomous_workflow_agent",
        "model": "openai/gpt-4o-mini",
        "db": "postgresql" if db_ok else "unreachable",
        "redis": "ok" if redis_ok else "unreachable",
    }


# ── workflow ──────────────────────────────────────────────────────────────────

@router.post("/run", response_model=WorkflowRunResponse)
async def trigger_workflow(
    request: WorkflowTriggerRequest,
    background_tasks: BackgroundTasks,
) -> WorkflowRunResponse:
    engine = get_workflow_engine()
    run_id = str(uuid.uuid4())
    background_tasks.add_task(
        engine.execute_workflow,
        request.max_emails,
        request.generate_report,
        run_id,
    )
    return WorkflowRunResponse(
        run_id=run_id,
        status=WorkflowStatus.RUNNING,
        message="Workflow started — connect to WebSocket for live updates",
        ws_url=f"/api/ws/runs/{run_id}",
    )


@router.get("/runs", response_model=list[WorkflowRun])
async def list_runs(limit: int = 20, status: str | None = None) -> list[WorkflowRun]:
    return await get_state_store().list_runs(limit=limit, status=status)


@router.get("/runs/{run_id}", response_model=WorkflowRun)
async def get_run(run_id: str) -> WorkflowRun:
    run = await get_state_store().get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str) -> dict[str, str]:
    store = get_state_store()
    run = await store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    run.status = WorkflowStatus.FAILED
    run.error_message = "Manually stopped by user"
    run.completed_at = datetime.now(timezone.utc)
    await store.update_run(run)
    return {"status": "stopped", "run_id": run_id}


# ── WebSocket — real-time workflow events ─────────────────────────────────────

@router.websocket("/ws/runs/{run_id}")
async def workflow_websocket(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()

    # If the run already finished before the client connected, send the
    # final event immediately without touching Redis.
    run = await get_state_store().get_run(run_id)
    if run and run.status not in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING):
        await websocket.send_json({
            "type": "workflow_complete",
            "status": run.status.value,
            "emails_processed": run.emails_processed,
            "report_path": run.report_path,
        })
        await websocket.close()
        return

    # Subscribe via Redis pub/sub — works across any number of worker processes.
    try:
        async with subscribe_events(run_id) as queue:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    await websocket.send_json(event)
                    if event.get("type") == "workflow_complete":
                        break
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected from run {run_id}")
    finally:
        await websocket.close()


# ── analytics ─────────────────────────────────────────────────────────────────

@router.get("/analytics/summary")
async def get_analytics_summary(days: int = 7) -> dict[str, Any]:
    return await get_state_store().get_analytics_summary(days=days)


@router.get("/analytics/categories")
async def get_category_distribution(days: int = 7) -> dict[str, Any]:
    summary = await get_state_store().get_analytics_summary(days=days)
    return {"categories": summary.get("category_distribution", {})}


# ── processed emails ──────────────────────────────────────────────────────────

@router.get("/emails")
async def list_emails(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    category: str | None = None,
    urgency: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    emails, total = await get_state_store().get_emails(
        page=page, limit=limit, category=category, urgency=urgency, search=q
    )
    return {
        "emails": [e.model_dump() for e in emails],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // limit)),
    }


@router.get("/emails/priority-inbox")
async def get_priority_inbox(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    emails = await get_state_store().get_priority_inbox(limit=limit)
    return {"emails": [e.model_dump() for e in emails], "total": len(emails)}


@router.get("/emails/{email_id}")
async def get_email(email_id: str) -> dict[str, Any]:
    email = await get_state_store().get_email_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email.model_dump()


# ── draft replies ─────────────────────────────────────────────────────────────

@router.get("/emails/{email_id}/draft")
async def get_draft(email_id: str) -> dict[str, Any]:
    draft = await get_state_store().get_draft(email_id)
    if not draft:
        raise HTTPException(status_code=404, detail="No draft found for this email")
    return draft.model_dump()


@router.post("/emails/{email_id}/draft/generate")
async def generate_draft(email_id: str) -> dict[str, Any]:
    from autonomous_workflow_agent.app.ai.draft_generator import generate_draft_reply

    store = get_state_store()
    email = await store.get_email_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    from autonomous_workflow_agent.app.workflows.models import (
        EmailCategory,
        EmailClassification,
        EmailData,
    )
    email_data = EmailData(
        message_id=email.email_id,
        subject=email.subject,
        sender=email.sender,
        recipient="",
        date=email.date,
        body=email.body_preview,
        snippet=email.body_preview,
        classification=EmailClassification(
            category=EmailCategory(email.category),
            confidence=email.classification_confidence,
            reasoning="",
        ),
    )
    draft = await generate_draft_reply(email_data)
    if not draft:
        raise HTTPException(status_code=500, detail="Draft generation failed. Check your OPENAI_API_KEY.")
    await store.save_draft(draft)
    return draft.model_dump()


@router.get("/drafts")
async def list_drafts(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    drafts = await get_state_store().list_drafts(limit=limit)
    return {"drafts": drafts, "total": len(drafts)}


# ── action items ──────────────────────────────────────────────────────────────

@router.get("/actions")
async def list_actions(
    completed: bool | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    items = await get_state_store().get_action_items(completed=completed, priority=priority)
    return {"items": [i.model_dump() for i in items], "total": len(items)}


@router.put("/actions/{item_id}/toggle")
async def toggle_action(item_id: str) -> dict[str, Any]:
    completed = await get_state_store().toggle_action_item(item_id)
    return {"item_id": item_id, "completed": completed}


@router.delete("/actions/{item_id}")
async def delete_action(item_id: str) -> dict[str, str]:
    await get_state_store().delete_action_item(item_id)
    return {"status": "deleted", "item_id": item_id}


@router.delete("/actions/completed/clear")
async def clear_completed_actions() -> dict[str, Any]:
    count = await get_state_store().delete_completed_actions()
    return {"status": "cleared", "deleted": count}


# ── export ────────────────────────────────────────────────────────────────────

@router.get("/export/csv")
async def export_csv(days: int = Query(30, ge=1, le=365)) -> StreamingResponse:
    csv_content = await get_state_store().export_emails_csv(days=days)
    filename = f"emails_last_{days}_days.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── schedule ──────────────────────────────────────────────────────────────────

@router.get("/schedule")
async def get_schedule() -> dict[str, Any]:
    from autonomous_workflow_agent.app.workflows.scheduler import get_workflow_scheduler
    store = get_state_store()
    config = await store.get_schedule()
    scheduler = get_workflow_scheduler()
    next_run = scheduler.get_next_run()
    data = config.model_dump()
    data["next_run"] = next_run
    data["is_active"] = scheduler.is_active
    return data


@router.post("/schedule")
async def save_schedule(config: ScheduleConfig) -> dict[str, Any]:
    from autonomous_workflow_agent.app.workflows.scheduler import get_workflow_scheduler
    store = get_state_store()
    await store.save_schedule(config)
    scheduler = get_workflow_scheduler()
    await scheduler.configure(config)
    next_run = scheduler.get_next_run()
    data = config.model_dump()
    data["next_run"] = next_run
    data["is_active"] = scheduler.is_active
    return data


@router.delete("/schedule")
async def disable_schedule() -> dict[str, str]:
    from autonomous_workflow_agent.app.workflows.scheduler import get_workflow_scheduler
    store = get_state_store()
    config = await store.get_schedule()
    config.enabled = False
    await store.save_schedule(config)
    scheduler = get_workflow_scheduler()
    await scheduler.configure(config)
    return {"status": "disabled"}


# ── settings ──────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings_endpoint() -> dict[str, Any]:
    settings = await get_state_store().get_settings()
    return settings.model_dump()


@router.post("/settings")
async def save_settings_endpoint(settings: UserSettings) -> dict[str, Any]:
    await get_state_store().save_settings(settings)
    return settings.model_dump()


# ── reports ───────────────────────────────────────────────────────────────────

@router.get("/reports")
async def list_reports() -> dict[str, Any]:
    reports_dir = get_project_root() / "data" / "reports"
    if not reports_dir.exists():
        return {"reports": []}

    reports: list[dict[str, Any]] = []
    for f in sorted(reports_dir.glob("report_*.md"), reverse=True):
        entry: dict[str, Any] = {
            "filename": f.name,
            "created_at": f.stat().st_mtime,
            "size": f.stat().st_size,
            "urgency_summary": None,
        }
        try:
            content = f.read_text(encoding="utf-8")
            imp = re.search(r"\*\*Important:\*\*\s*(\d+)", content)
            rev = re.search(r"\*\*Needed Review:\*\*\s*(\d+)", content)
            imp_count = int(imp.group(1)) if imp else 0
            rev_count = int(rev.group(1)) if rev else 0
            entry["urgency_summary"] = {
                "label": "Important" if imp_count > 0 else ("Review Needed" if rev_count > 0 else "Routine"),
                "color": "red" if imp_count > 0 else ("orange" if rev_count > 0 else "green"),
                "important": imp_count,
                "review": rev_count,
            }
        except Exception:
            pass
        reports.append(entry)

    return {"reports": reports}


@router.get("/reports/{filename}")
async def get_report(filename: str) -> dict[str, Any]:
    # Path traversal guard
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    report_path = get_project_root() / "data" / "reports" / filename
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "filename": filename,
        "content": report_path.read_text(encoding="utf-8"),
        "created_at": report_path.stat().st_mtime,
        "size": report_path.stat().st_size,
    }


# ── Gmail webhooks ────────────────────────────────────────────────────────────

@router.post("/webhooks/gmail")
async def gmail_webhook(request: dict) -> dict[str, Any]:
    from autonomous_workflow_agent.app.auth.gmail_push import get_gmail_push_manager
    mgr = get_gmail_push_manager()
    history_id = mgr.process_notification(request)
    return {"status": "ok", "history_id": history_id} if history_id else {"status": "ignored"}


@router.post("/gmail/watch")
async def enable_gmail_watch(topic_name: str) -> dict[str, Any]:
    from autonomous_workflow_agent.app.auth.gmail_push import get_gmail_push_manager
    mgr = get_gmail_push_manager()
    result = mgr.setup_watch(topic_name)
    return {"status": "ok", "watch_response": result}


# ── Smart Briefing ────────────────────────────────────────────────────────────

@router.get("/briefing")
async def get_briefing(days: int = Query(7, ge=1, le=30), refresh: bool = False) -> dict[str, Any]:
    store = get_state_store()

    if not refresh:
        cached = await store.get_briefing_cache()
        if cached:
            return {
                "content": cached["content"],
                "generated_at": cached["generated_at"],
                "email_count": cached["email_count"],
                "cached": True,
            }

    emails_raw, total = await store.get_emails(page=1, limit=100)
    if not emails_raw:
        return {
            "content": "## No Data\n\nRun a workflow first to populate your inbox.",
            "cached": False,
        }

    from autonomous_workflow_agent.app.ai.briefing_generator import generate_briefing
    email_dicts = [e.model_dump() for e in emails_raw]
    content = await generate_briefing(email_dicts, period_days=days)
    await store.save_briefing_cache(content, len(emails_raw))
    return {
        "content": content,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "email_count": len(emails_raw),
        "cached": False,
    }


# ── AI Email Composer ─────────────────────────────────────────────────────────

@router.post("/compose")
async def compose_email(request: ComposeRequest) -> dict[str, Any]:
    from autonomous_workflow_agent.app.ai.email_composer import compose_email as _compose
    result = await _compose(
        to=request.to,
        intent=request.intent,
        tone=request.tone,
        context=request.context,
        thread_context=request.thread_context,
    )
    if not result:
        raise HTTPException(
            status_code=500,
            detail="Email composition failed. Check your OPENAI_API_KEY.",
        )
    return result


# ── Topic Clustering ──────────────────────────────────────────────────────────

@router.get("/topics")
async def get_topics(limit: int = Query(60, ge=5, le=200)) -> dict[str, Any]:
    store = get_state_store()
    emails_raw, _ = await store.get_emails(page=1, limit=limit)
    if not emails_raw:
        return {"topics": [], "email_count": 0}

    from autonomous_workflow_agent.app.ai.topic_clusterer import cluster_topics
    email_dicts = [e.model_dump() for e in emails_raw]
    topics = await cluster_topics(email_dicts)
    return {"topics": topics, "email_count": len(emails_raw)}


# ── Contact Intelligence ──────────────────────────────────────────────────────

@router.get("/contacts")
async def get_contacts(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    contacts = await get_state_store().get_contacts(limit=limit)
    return {"contacts": contacts, "total": len(contacts)}


# ── Anomaly Detection ─────────────────────────────────────────────────────────

@router.get("/analytics/anomalies")
async def get_anomalies() -> dict[str, Any]:
    return await get_state_store().get_anomalies()


# ── Email Translation ─────────────────────────────────────────────────────────

@router.get("/emails/{email_id}/translation")
async def get_translation(email_id: str) -> dict[str, Any]:
    translation = await get_state_store().get_translation(email_id)
    if not translation:
        raise HTTPException(status_code=404, detail="No translation found")
    return translation


@router.post("/emails/{email_id}/translate")
async def translate_email(email_id: str) -> dict[str, Any]:
    store = get_state_store()
    email = await store.get_email_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    from autonomous_workflow_agent.app.ai.openai_client import get_openai_client

    _TRANSLATE_TOOL = [
        {
            "type": "function",
            "function": {
                "name": "translate_email",
                "description": "Detect language and translate email content to English",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "detected_language": {"type": "string"},
                        "is_english": {"type": "boolean"},
                        "translated_subject": {"type": "string"},
                        "translated_body": {"type": "string"},
                    },
                    "required": [
                        "detected_language", "is_english",
                        "translated_subject", "translated_body",
                    ],
                },
            },
        }
    ]

    client = get_openai_client()
    result = await client.complete(
        system="Detect the language of this email and translate it to English if not already English.",
        user=f"Subject: {email.subject}\n\nBody:\n{email.body_preview}",
        tools=_TRANSLATE_TOOL,
        tool_choice={"type": "function", "function": {"name": "translate_email"}},
        max_tokens=600,
    )

    if not result.success or not result.tool_result:
        raise HTTPException(status_code=500, detail="Translation failed. Check your OPENAI_API_KEY.")

    inp = result.tool_result["input"]
    await store.save_translation(
        email_id=email_id,
        language=inp["detected_language"],
        translated_subject=inp["translated_subject"],
        translated_body=inp["translated_body"],
    )
    return {
        "email_id": email_id,
        "detected_language": inp["detected_language"],
        "is_english": inp["is_english"],
        "translated_subject": inp["translated_subject"],
        "translated_body": inp["translated_body"],
    }


# ── Follow-up Tracker ─────────────────────────────────────────────────────────

@router.get("/follow-ups")
async def list_follow_ups(completed: bool | None = None) -> dict[str, Any]:
    items = await get_state_store().get_follow_ups(completed=completed)
    overdue = [
        f for f in items
        if not f["completed"]
        and f["follow_up_date"] < datetime.now(timezone.utc).date().isoformat()
    ]
    return {"items": items, "total": len(items), "overdue": len(overdue)}


@router.post("/follow-ups")
async def add_follow_up(follow_up: FollowUp) -> dict[str, Any]:
    await get_state_store().add_follow_up(follow_up)
    return follow_up.model_dump()


@router.put("/follow-ups/{item_id}/toggle")
async def toggle_follow_up(item_id: str) -> dict[str, Any]:
    completed = await get_state_store().toggle_follow_up(item_id)
    return {"item_id": item_id, "completed": completed}


@router.delete("/follow-ups/{item_id}")
async def delete_follow_up(item_id: str) -> dict[str, str]:
    await get_state_store().delete_follow_up(item_id)
    return {"status": "deleted", "item_id": item_id}


# ── Smart Search ──────────────────────────────────────────────────────────────

@router.get("/search")
async def smart_search(
    q: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    emails, total = await get_state_store().get_emails(page=page, limit=limit, search=q)
    return {
        "emails": [e.model_dump() for e in emails],
        "total": total,
        "query": q,
        "page": page,
        "pages": max(1, -(-total // limit)),
    }
