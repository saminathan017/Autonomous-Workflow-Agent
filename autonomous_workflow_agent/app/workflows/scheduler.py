from __future__ import annotations

from loguru import logger

from autonomous_workflow_agent.app.workflows.models import ScheduleConfig, ScheduleType


class WorkflowScheduler:
    """
    APScheduler-backed async scheduler.
    Must be started within the FastAPI lifespan (inside the active event loop).
    """

    def __init__(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        self._scheduler.start()
        logger.info("Workflow scheduler started")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Workflow scheduler stopped")

    async def configure(self, config: ScheduleConfig) -> None:
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        if self._scheduler.get_job("workflow_auto"):
            self._scheduler.remove_job("workflow_auto")

        if not config.enabled:
            logger.info("Auto-scheduler disabled")
            return

        if config.schedule_type == ScheduleType.DAILY:
            trigger = CronTrigger(hour=config.cron_hour, minute=config.cron_minute)
            desc = f"daily at {config.cron_hour:02d}:{config.cron_minute:02d} UTC"
        else:
            trigger = IntervalTrigger(hours=config.interval_hours)
            desc = f"every {config.interval_hours}h"

        self._scheduler.add_job(
            _run_scheduled_workflow,
            trigger=trigger,
            id="workflow_auto",
            kwargs={
                "max_emails": config.max_emails,
                "generate_report": config.generate_report,
            },
            replace_existing=True,
        )
        logger.info(f"Scheduled workflow configured: {desc}, max_emails={config.max_emails}")

    def get_next_run(self) -> str | None:
        job = self._scheduler.get_job("workflow_auto")
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None

    @property
    def is_active(self) -> bool:
        return self._scheduler.running and bool(self._scheduler.get_job("workflow_auto"))


async def _run_scheduled_workflow(max_emails: int, generate_report: bool) -> None:
    from autonomous_workflow_agent.app.workflows.engine import get_workflow_engine
    from autonomous_workflow_agent.app.workflows.state_store import get_state_store

    logger.info("⏰ Scheduled workflow triggered")
    store = get_state_store()
    config = await store.get_schedule()

    try:
        engine = get_workflow_engine()
        run = await engine.execute_workflow(
            max_emails=max_emails, generate_report=generate_report
        )
        config.last_run = run.completed_at
        await store.save_schedule(config)
        logger.info(f"Scheduled run completed: {run.status}")
    except Exception as exc:
        logger.error(f"Scheduled workflow failed: {exc}")


# ── singleton ─────────────────────────────────────────────────────────────────

_scheduler: WorkflowScheduler | None = None


def get_workflow_scheduler() -> WorkflowScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = WorkflowScheduler()
    return _scheduler
