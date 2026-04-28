from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from autonomous_workflow_agent.app.config import get_settings
from autonomous_workflow_agent.app.workflows.event_bus import publish_event
from autonomous_workflow_agent.app.workflows.models import (
    EmailData,
    SheetRow,
    StepLog,
    StepStatus,
    UrgencyLabel,
    WorkflowRun,
    WorkflowStatus,
)
from autonomous_workflow_agent.app.workflows.state_store import get_state_store
from autonomous_workflow_agent.app.workflows.tasks.gmail_reader import get_gmail_reader
from autonomous_workflow_agent.app.workflows.tasks.report_builder import get_report_builder
from autonomous_workflow_agent.app.workflows.tasks.sheets_writer import get_sheets_writer


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_sheet_rows(emails: list[EmailData]) -> list[SheetRow]:
    rows: list[SheetRow] = []
    ts = _now().strftime("%Y-%m-%d %H:%M:%S")
    for email in emails:
        rows.append(
            SheetRow(
                email_id=email.message_id,
                subject=email.subject,
                sender=email.sender,
                date=email.date,
                summary=email.snippet[:200],
                category=email.classification.category.value
                if email.classification
                else "GENERAL",
                sentiment=email.sentiment.sentiment.value
                if email.sentiment
                else "NEUTRAL",
                urgency_label=email.sentiment.urgency_label.value
                if email.sentiment
                else UrgencyLabel.LOW.value,
                processed_at=ts,
            )
        )
    return rows


class WorkflowEngine:
    """
    Async workflow orchestrator with Redis pub/sub WebSocket event bus,
    retry logic, graceful degradation, and AI enrichment steps.

    Events are published to Redis so any server worker process can receive
    them — enabling true multi-process / multi-worker deployments.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._store = get_state_store()

    # ── pub/sub ───────────────────────────────────────────────────────────────

    def _emit(self, run_id: str, event: dict[str, Any]) -> None:
        """Fire-and-forget Redis publish — never blocks the workflow step."""
        asyncio.create_task(publish_event(run_id, event))

    # ── step runner ───────────────────────────────────────────────────────────

    async def _run_step(
        self,
        run_id: str,
        step_name: str,
        coro,
        *,
        critical: bool = True,
    ) -> tuple[bool, Any]:
        max_retries = self._settings.workflow_max_retries
        delay = self._settings.workflow_retry_delay_seconds

        self._emit(run_id, {"type": "step_start", "step": step_name})

        for attempt in range(max_retries + 1):
            step = StepLog(
                step_name=step_name,
                status=StepStatus.RUNNING,
                started_at=_now(),
                retry_count=attempt,
            )
            try:
                result = await coro()
                step.status = StepStatus.COMPLETED
                step.completed_at = _now()
                await self._store.add_step_log(run_id, step)
                self._emit(
                    run_id, {"type": "step_done", "step": step_name, "success": True}
                )
                return True, result
            except Exception as exc:
                err = str(exc)
                logger.warning(f"Step '{step_name}' attempt {attempt + 1} failed: {err}")
                if attempt < max_retries:
                    await asyncio.sleep(delay * (2**attempt))
                else:
                    step.status = StepStatus.FAILED
                    step.completed_at = _now()
                    step.error_message = err
                    await self._store.add_step_log(run_id, step)
                    self._emit(
                        run_id,
                        {"type": "step_done", "step": step_name, "success": False, "error": err},
                    )
                    if critical:
                        raise
                    return False, None

        return False, None

    # ── main workflow ─────────────────────────────────────────────────────────

    async def execute_workflow(
        self,
        max_emails: int = 10,
        generate_report: bool = True,
        run_id: str | None = None,
    ) -> WorkflowRun:
        if run_id is None:
            run_id = str(uuid.uuid4())

        run = WorkflowRun(run_id=run_id, status=WorkflowStatus.RUNNING, started_at=_now())
        await self._store.create_run(run)
        self._emit(run_id, {"type": "workflow_start", "run_id": run_id})
        logger.info(f"Workflow {run_id} started")

        try:
            # ── Step 1: Fetch & analyse emails (critical) ─────────────────────
            gmail = get_gmail_reader()
            _, emails = await self._run_step(
                run_id,
                "fetch_emails",
                lambda: gmail.fetch_emails(max_results=max_emails),
                critical=True,
            )
            emails = emails or []
            run.emails_processed = len(emails)

            # Cache classifications for analytics
            for email in emails:
                if email.classification and email.sentiment:
                    try:
                        await self._store.cache_classification(
                            email_id=email.message_id,
                            category=email.classification.category.value,
                            sentiment=email.sentiment.sentiment.value,
                            urgency_score=email.sentiment.urgency_score,
                            confidence=email.classification.confidence,
                        )
                    except Exception:
                        pass

            self._emit(run_id, {"type": "emails_fetched", "count": len(emails)})

            # ── Step 2: Store emails for browsing (non-critical) ──────────────
            async def _store_emails():
                for email in emails:
                    await self._store.store_email(email, run_id)
                return len(emails)

            await self._run_step(run_id, "store_emails", _store_emails, critical=False)

            # ── Step 3: Write to Google Sheets (non-critical) ─────────────────
            sheets = get_sheets_writer()
            sheet_rows = _make_sheet_rows(emails)
            await self._run_step(
                run_id,
                "write_to_sheets",
                lambda: sheets.write_rows(sheet_rows),
                critical=False,
            )

            # ── Step 4: Generate AI draft replies (non-critical) ──────────────
            user_settings = await self._store.get_settings()
            if user_settings.auto_draft_enabled and emails:
                from autonomous_workflow_agent.app.ai.draft_generator import generate_draft_reply

                async def _generate_drafts():
                    candidates = [
                        e for e in emails
                        if e.sentiment and (
                            e.sentiment.requires_human
                            or (e.classification and e.classification.category.value
                                in ("URGENT", "CUSTOMER_INQUIRY", "INVOICE"))
                        )
                    ]
                    drafts_saved = 0
                    for email in candidates[:5]:  # cap at 5 per run
                        draft = await generate_draft_reply(email, run_id)
                        if draft:
                            await self._store.save_draft(draft)
                            drafts_saved += 1
                    return drafts_saved

                ok, drafts_count = await self._run_step(
                    run_id, "generate_drafts", _generate_drafts, critical=False
                )
                if ok and drafts_count:
                    self._emit(run_id, {"type": "drafts_ready", "count": drafts_count})

            # ── Step 5: Extract action items (non-critical) ───────────────────
            if user_settings.action_items_enabled and emails:
                from autonomous_workflow_agent.app.ai.action_extractor import extract_action_items

                async def _extract_actions():
                    all_items = []
                    tasks = [extract_action_items(e, run_id) for e in emails]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for result in results:
                        if isinstance(result, list):
                            all_items.extend(result)
                    await self._store.save_action_items(all_items)
                    return len(all_items)

                ok, actions_count = await self._run_step(
                    run_id, "extract_actions", _extract_actions, critical=False
                )
                if ok and actions_count:
                    self._emit(run_id, {"type": "actions_extracted", "count": actions_count})

            # ── Step 6: Generate AI report (non-critical) ─────────────────────
            if generate_report and emails:
                builder = get_report_builder()
                ok, report_data = await self._run_step(
                    run_id,
                    "generate_report",
                    lambda: builder.build_report(emails),
                    critical=False,
                )
                if ok and report_data:
                    report_path = builder.save_report(report_data)
                    run.report_path = str(report_path)
                    self._emit(
                        run_id,
                        {"type": "report_ready", "path": str(report_path)},
                    )

            run.status = WorkflowStatus.COMPLETED
            run.completed_at = _now()

        except Exception as exc:
            logger.error(f"Workflow {run_id} failed: {exc}")
            run.status = WorkflowStatus.FAILED
            run.error_message = str(exc)
            run.completed_at = _now()

        await self._store.update_run(run)
        self._emit(
            run_id,
            {
                "type": "workflow_complete",
                "status": run.status.value,
                "emails_processed": run.emails_processed,
                "report_path": run.report_path,
            },
        )
        logger.info(
            f"Workflow {run_id} → {run.status.value} ({run.emails_processed} emails)"
        )
        return run


# ── singleton ─────────────────────────────────────────────────────────────────

_engine: WorkflowEngine | None = None


def get_workflow_engine() -> WorkflowEngine:
    global _engine
    if _engine is None:
        _engine = WorkflowEngine()
    return _engine
