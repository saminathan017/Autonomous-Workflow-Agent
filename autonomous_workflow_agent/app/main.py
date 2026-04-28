from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from autonomous_workflow_agent.app.api.routes import router
from autonomous_workflow_agent.app.config import get_settings, get_reports_dir
from autonomous_workflow_agent.app.utils.logging import configure_logging, get_logger
from autonomous_workflow_agent.app.workflows.event_bus import close_redis, ping_redis
from autonomous_workflow_agent.app.workflows.scheduler import get_workflow_scheduler
from autonomous_workflow_agent.app.workflows.state_store import get_state_store

_MAX_REPORTS = 50  # keep newest N; delete the rest on startup


def _purge_old_reports(max_keep: int = _MAX_REPORTS) -> int:
    """Delete oldest report files, keeping the newest `max_keep`. Returns count deleted."""
    reports_dir = get_reports_dir()
    files = sorted(reports_dir.glob("report_*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    to_delete = files[max_keep:]
    for f in to_delete:
        f.unlink(missing_ok=True)
    return len(to_delete)

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("━━━ Autonomous Workflow Agent starting ━━━")
    logger.info(f"AI Model : OpenAI {settings.openai_model}")
    logger.info(f"DB       : PostgreSQL (pool {settings.db_pool_min}-{settings.db_pool_max})")
    logger.info(f"Event bus: Redis {settings.redis_url}")
    logger.info(f"Budget   : {settings.openai_max_calls_per_run} OpenAI calls / run")
    logger.info(f"Rate cap : {settings.openai_concurrency_limit} concurrent requests")

    store = get_state_store()
    await store.initialize()
    logger.info("PostgreSQL pool ready — tables verified — stale runs cleaned")

    if not await ping_redis():
        raise RuntimeError(
            f"Redis is unreachable at {settings.redis_url}. "
            "Start Redis before launching the app."
        )
    logger.info("Redis connection ready — multi-process pub/sub active")

    deleted = _purge_old_reports(_MAX_REPORTS)
    if deleted:
        logger.info(f"Report cleanup: removed {deleted} old report(s), keeping newest {_MAX_REPORTS}")

    # Only the worker that wins the PostgreSQL advisory lock runs the scheduler.
    # All other workers skip it, preventing duplicate scheduled runs.
    is_scheduler_leader = await store.try_acquire_scheduler_lock()
    scheduler = get_workflow_scheduler()
    if is_scheduler_leader:
        scheduler.start()
        saved_config = await store.get_schedule()
        if saved_config.enabled:
            await scheduler.configure(saved_config)
            logger.info(f"Auto-scheduler resumed ({saved_config.schedule_type})")
        logger.info("Scheduler leader: this worker owns the schedule")
    else:
        logger.info("Scheduler follower: another worker owns the schedule")

    yield

    scheduler.stop()
    await close_redis()
    await store.close()
    logger.info("━━━ Autonomous Workflow Agent stopped ━━━")


app = FastAPI(
    title="Autonomous Workflow Agent",
    description="Gmail → OpenAI Analysis → Sheets → Reports",
    version="4.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Locked to configured origins (not wildcard *)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API Key authentication middleware ─────────────────────────────────────────
# Only enforced when API_SECRET_KEY is set in .env; safe to leave empty for local dev
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if settings.api_secret_key and request.url.path.startswith("/api/"):
        api_key = request.headers.get("X-API-Key", "")
        if api_key != settings.api_secret_key:
            return JSONResponse(
                {"detail": "Unauthorized — X-API-Key header required"},
                status_code=401,
            )
    return await call_next(request)


# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(router, prefix="/api")

# ── Frontend static files ─────────────────────────────────────────────────────
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info(f"Frontend served from {frontend_dir}")
else:
    logger.warning(f"Frontend directory not found: {frontend_dir}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "autonomous_workflow_agent.app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
