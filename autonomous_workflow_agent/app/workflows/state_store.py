from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
from loguru import logger

from autonomous_workflow_agent.app.config import get_settings
from autonomous_workflow_agent.app.workflows.models import (
    ActionItem,
    ActionItemPriority,
    DraftReply,
    ProcessedEmail,
    ScheduleConfig,
    ScheduleType,
    StepLog,
    StepStatus,
    UserSettings,
    WorkflowRun,
    WorkflowStatus,
)

# ── PostgreSQL schema ─────────────────────────────────────────────────────────

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS workflow_runs (
        run_id          TEXT PRIMARY KEY,
        status          TEXT NOT NULL,
        started_at      TIMESTAMPTZ NOT NULL,
        completed_at    TIMESTAMPTZ,
        error_message   TEXT,
        emails_processed INTEGER DEFAULT 0,
        report_path     TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_runs_status  ON workflow_runs(status)",
    "CREATE INDEX IF NOT EXISTS idx_runs_started ON workflow_runs(started_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS step_logs (
        id              BIGSERIAL PRIMARY KEY,
        run_id          TEXT NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
        step_name       TEXT NOT NULL,
        status          TEXT NOT NULL,
        started_at      TIMESTAMPTZ,
        completed_at    TIMESTAMPTZ,
        error_message   TEXT,
        retry_count     INTEGER DEFAULT 0,
        metadata        TEXT DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_steps_run ON step_logs(run_id)",
    """
    CREATE TABLE IF NOT EXISTS analytics (
        id           BIGSERIAL PRIMARY KEY,
        timestamp    TIMESTAMPTZ NOT NULL,
        metric_name  TEXT NOT NULL,
        metric_value DOUBLE PRECISION NOT NULL,
        metadata     TEXT DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_analytics_name ON analytics(metric_name, timestamp)",
    """
    CREATE TABLE IF NOT EXISTS email_classifications (
        email_id      TEXT PRIMARY KEY,
        category      TEXT NOT NULL,
        sentiment     TEXT NOT NULL,
        urgency_score DOUBLE PRECISION NOT NULL,
        confidence    DOUBLE PRECISION NOT NULL,
        classified_at TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_class_cat ON email_classifications(category)",
    """
    CREATE TABLE IF NOT EXISTS processed_emails (
        email_id                  TEXT PRIMARY KEY,
        run_id                    TEXT,
        subject                   TEXT,
        sender                    TEXT,
        date                      TEXT,
        body_preview              TEXT,
        category                  TEXT DEFAULT 'GENERAL',
        sentiment                 TEXT DEFAULT 'NEUTRAL',
        urgency_label             TEXT DEFAULT 'Take Your Time',
        urgency_score             DOUBLE PRECISION DEFAULT 0.0,
        requires_human            BOOLEAN DEFAULT FALSE,
        classification_confidence DOUBLE PRECISION DEFAULT 0.0,
        processed_at              TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_emails_urgency  ON processed_emails(urgency_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_emails_category ON processed_emails(category)",
    "CREATE INDEX IF NOT EXISTS idx_emails_run      ON processed_emails(run_id)",
    """
    CREATE TABLE IF NOT EXISTS draft_replies (
        id           TEXT PRIMARY KEY,
        email_id     TEXT NOT NULL,
        run_id       TEXT,
        subject      TEXT,
        sender       TEXT,
        draft_content TEXT NOT NULL,
        tone         TEXT DEFAULT 'professional',
        generated_at TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_drafts_email ON draft_replies(email_id)",
    """
    CREATE TABLE IF NOT EXISTS action_items (
        id         TEXT PRIMARY KEY,
        email_id   TEXT NOT NULL,
        run_id     TEXT,
        task       TEXT NOT NULL,
        priority   TEXT DEFAULT 'MEDIUM',
        due_date   TEXT,
        completed  BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_actions_priority ON action_items(priority, completed)",
    """
    CREATE TABLE IF NOT EXISTS schedule_config (
        id              INTEGER PRIMARY KEY DEFAULT 1,
        enabled         BOOLEAN DEFAULT FALSE,
        schedule_type   TEXT DEFAULT 'daily',
        interval_hours  INTEGER DEFAULT 6,
        cron_hour       INTEGER DEFAULT 9,
        cron_minute     INTEGER DEFAULT 0,
        max_emails      INTEGER DEFAULT 10,
        generate_report BOOLEAN DEFAULT TRUE,
        next_run        TIMESTAMPTZ,
        last_run        TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_settings (
        id            INTEGER PRIMARY KEY DEFAULT 1,
        settings_json TEXT DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS follow_ups (
        id             TEXT PRIMARY KEY,
        email_id       TEXT,
        subject        TEXT,
        sender         TEXT,
        follow_up_date TEXT NOT NULL,
        note           TEXT DEFAULT '',
        completed      BOOLEAN DEFAULT FALSE,
        created_at     TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_followups_date ON follow_ups(follow_up_date, completed)",
    """
    CREATE TABLE IF NOT EXISTS email_translations (
        email_id            TEXT PRIMARY KEY,
        original_language   TEXT,
        translated_subject  TEXT,
        translated_body     TEXT,
        translated_at       TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS briefing_cache (
        id           INTEGER PRIMARY KEY DEFAULT 1,
        content      TEXT NOT NULL,
        generated_at TIMESTAMPTZ NOT NULL,
        email_count  INTEGER DEFAULT 0
    )
    """,
]


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _row_to_step(r: asyncpg.Record) -> StepLog:
    return StepLog(
        step_name=r["step_name"],
        status=StepStatus(r["status"].upper()),
        started_at=r["started_at"],
        completed_at=r["completed_at"],
        error_message=r["error_message"],
        retry_count=r["retry_count"] or 0,
        metadata=json.loads(r["metadata"] or "{}"),
    )


def _row_to_email(r: asyncpg.Record) -> ProcessedEmail:
    return ProcessedEmail(
        email_id=r["email_id"],
        run_id=r["run_id"] or "",
        subject=r["subject"] or "",
        sender=r["sender"] or "",
        date=r["date"] or "",
        body_preview=r["body_preview"] or "",
        category=r["category"] or "GENERAL",
        sentiment=r["sentiment"] or "NEUTRAL",
        urgency_label=r["urgency_label"] or "Take Your Time",
        urgency_score=r["urgency_score"] or 0.0,
        requires_human=bool(r["requires_human"]),
        classification_confidence=r["classification_confidence"] or 0.0,
        processed_at=r["processed_at"].isoformat() if r["processed_at"] else "",
        has_draft=bool(r.get("has_draft", 0)),
        action_count=r.get("action_count", 0) or 0,
    )


class StateStore:
    """Async PostgreSQL state store — asyncpg connection pool."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        self._leader_conn: asyncpg.Connection | None = None

    # ── initialisation ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        settings = get_settings()
        self._pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
            command_timeout=60,
        )
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for stmt in _SCHEMA_STATEMENTS:
                    await conn.execute(stmt)
        # Mark any runs stuck in RUNNING/PENDING as FAILED (crash recovery)
        await self._cleanup_stale_runs()
        logger.info("PostgreSQL database ready")

    async def close(self) -> None:
        if self._leader_conn is not None:
            await self._leader_conn.close()
            self._leader_conn = None
        if self._pool:
            await self._pool.close()
            self._pool = None

    # ── multi-process scheduler lock ──────────────────────────────────────────

    _SCHEDULER_LOCK_KEY = 42_424_242  # arbitrary stable integer

    async def try_acquire_scheduler_lock(self) -> bool:
        """
        PostgreSQL session-level advisory lock — only one worker wins.
        The lock is held for the lifetime of `_leader_conn` and released
        automatically when that connection is closed (process exit / shutdown).
        Returns True if this worker is the scheduler leader.
        """
        if self._pool is None:
            return False
        try:
            conn = await self._pool.acquire()
            acquired = await conn.fetchval(
                "SELECT pg_try_advisory_lock($1)", self._SCHEDULER_LOCK_KEY
            )
            if acquired:
                self._leader_conn = conn  # keep alive for the process lifetime
                return True
            await self._pool.release(conn)
            return False
        except Exception as exc:
            logger.warning(f"Scheduler lock attempt failed: {exc}")
            return False

    async def ping(self) -> bool:
        if self._pool is None:
            return False
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception as exc:
            logger.warning(f"PostgreSQL ping failed: {exc}")
            return False

    async def _cleanup_stale_runs(self) -> None:
        """Recover from server crash: mark stale RUNNING/PENDING runs as FAILED."""
        stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE workflow_runs
                   SET status = 'FAILED',
                       error_message = 'Terminated by system cleanup',
                       completed_at = NOW()
                   WHERE status IN ('RUNNING', 'PENDING')
                   AND started_at < $1""",
                stale_cutoff,
            )
        cleaned = int(result.split()[-1])
        if cleaned:
            logger.warning(f"Cleaned up {cleaned} stale workflow run(s)")

    # ── workflow runs ─────────────────────────────────────────────────────────

    async def create_run(self, run: WorkflowRun) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO workflow_runs (run_id, status, started_at, emails_processed)"
                " VALUES ($1, $2, $3, $4)",
                run.run_id, run.status.value, run.started_at, run.emails_processed,
            )

    async def update_run(self, run: WorkflowRun) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE workflow_runs
                   SET status=$1, completed_at=$2, error_message=$3,
                       emails_processed=$4, report_path=$5
                   WHERE run_id=$6""",
                run.status.value, run.completed_at, run.error_message,
                run.emails_processed, run.report_path, run.run_id,
            )

    async def get_run(self, run_id: str) -> WorkflowRun | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM workflow_runs WHERE run_id=$1", run_id
            )
            if not row:
                return None
            step_rows = await conn.fetch(
                "SELECT * FROM step_logs WHERE run_id=$1 ORDER BY id", run_id
            )
        return WorkflowRun(
            run_id=row["run_id"],
            status=WorkflowStatus(row["status"].upper()),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error_message=row["error_message"],
            emails_processed=row["emails_processed"] or 0,
            report_path=row["report_path"],
            steps=[_row_to_step(r) for r in step_rows],
        )

    async def list_runs(self, limit: int = 20, status: str | None = None) -> list[WorkflowRun]:
        async with self._pool.acquire() as conn:
            if status:
                run_rows = await conn.fetch(
                    "SELECT * FROM workflow_runs WHERE status=$1 ORDER BY started_at DESC LIMIT $2",
                    status, limit,
                )
            else:
                run_rows = await conn.fetch(
                    "SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT $1", limit
                )

            if not run_rows:
                return []

            run_ids = [r["run_id"] for r in run_rows]
            step_rows = await conn.fetch(
                "SELECT * FROM step_logs WHERE run_id = ANY($1::text[]) ORDER BY id",
                run_ids,
            )

        steps_by_run: dict[str, list[StepLog]] = {}
        for sr in step_rows:
            steps_by_run.setdefault(sr["run_id"], []).append(_row_to_step(sr))

        return [
            WorkflowRun(
                run_id=r["run_id"],
                status=WorkflowStatus(r["status"].upper()),
                started_at=r["started_at"],
                completed_at=r["completed_at"],
                error_message=r["error_message"],
                emails_processed=r["emails_processed"] or 0,
                report_path=r["report_path"],
                steps=steps_by_run.get(r["run_id"], []),
            )
            for r in run_rows
        ]

    # ── step logs ─────────────────────────────────────────────────────────────

    async def add_step_log(self, run_id: str, step: StepLog) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO step_logs
                   (run_id, step_name, status, started_at, completed_at,
                    error_message, retry_count, metadata)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                run_id, step.step_name, step.status.value,
                step.started_at, step.completed_at, step.error_message,
                step.retry_count, json.dumps(step.metadata),
            )

    # ── analytics ─────────────────────────────────────────────────────────────

    async def record_metric(
        self, metric_name: str, value: float, metadata: dict | None = None
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO analytics (timestamp, metric_name, metric_value, metadata)"
                " VALUES ($1,$2,$3,$4)",
                datetime.now(timezone.utc), metric_name, value,
                json.dumps(metadata or {}),
            )

    async def cache_classification(
        self,
        email_id: str,
        category: str,
        sentiment: str,
        urgency_score: float,
        confidence: float,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO email_classifications
                   (email_id, category, sentiment, urgency_score, confidence, classified_at)
                   VALUES ($1,$2,$3,$4,$5,$6)
                   ON CONFLICT (email_id) DO UPDATE
                   SET category=$2, sentiment=$3, urgency_score=$4,
                       confidence=$5, classified_at=$6""",
                email_id, category, sentiment, urgency_score, confidence,
                datetime.now(timezone.utc),
            )

    async def get_analytics_summary(self, days: int = 7) -> dict[str, Any]:
        cut = _cutoff(days)

        async with self._pool.acquire() as conn:
            # Run summary — fallback to all-time if no recent data
            rs = await conn.fetchrow(
                """SELECT COUNT(*) as total,
                          SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) as success,
                          COALESCE(SUM(emails_processed),0) as emails
                   FROM workflow_runs WHERE started_at >= $1""",
                cut,
            )
            if not (rs["total"] or 0):
                rs = await conn.fetchrow(
                    """SELECT COUNT(*) as total,
                              SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) as success,
                              COALESCE(SUM(emails_processed),0) as emails
                       FROM workflow_runs"""
                )

            # Category distribution
            cat_rows = await conn.fetch(
                "SELECT category, COUNT(*) c FROM email_classifications"
                " WHERE classified_at >= $1 GROUP BY category",
                cut,
            )
            cats = {r["category"]: r["c"] for r in cat_rows}
            if not cats:
                cat_rows = await conn.fetch(
                    "SELECT category, COUNT(*) c FROM email_classifications GROUP BY category"
                )
                cats = {r["category"]: r["c"] for r in cat_rows}

            # Sentiment distribution
            sent_rows = await conn.fetch(
                "SELECT sentiment, COUNT(*) c FROM email_classifications"
                " WHERE classified_at >= $1 GROUP BY sentiment",
                cut,
            )
            sents = {r["sentiment"]: r["c"] for r in sent_rows}
            if not sents:
                sent_rows = await conn.fetch(
                    "SELECT sentiment, COUNT(*) c FROM email_classifications GROUP BY sentiment"
                )
                sents = {r["sentiment"]: r["c"] for r in sent_rows}

            # Average urgency
            avg_urg = await conn.fetchval(
                "SELECT AVG(urgency_score) FROM email_classifications WHERE classified_at >= $1",
                cut,
            )
            if avg_urg is None:
                avg_urg = await conn.fetchval(
                    "SELECT AVG(urgency_score) FROM email_classifications"
                )

            active_actions = await conn.fetchval(
                "SELECT COUNT(*) FROM action_items WHERE completed=FALSE"
            )
            total_drafts = await conn.fetchval("SELECT COUNT(*) FROM draft_replies")

        total = rs["total"] or 0
        success = rs["success"] or 0
        return {
            "total_runs": total,
            "successful_runs": success,
            "failed_runs": total - success,
            "success_rate": round(success / total * 100, 1) if total else 0.0,
            "total_emails": rs["emails"] or 0,
            "category_distribution": cats,
            "sentiment_distribution": sents,
            "avg_urgency_score": round(float(avg_urg or 0.0), 3),
            "active_actions": active_actions or 0,
            "total_drafts": total_drafts or 0,
        }

    # ── processed emails ──────────────────────────────────────────────────────

    async def store_email(self, email: Any, run_id: str) -> None:
        category = email.classification.category.value if email.classification else "GENERAL"
        sentiment = email.sentiment.sentiment.value if email.sentiment else "NEUTRAL"
        urgency_score = email.sentiment.urgency_score if email.sentiment else 0.0
        urgency_label = email.sentiment.urgency_label.value if email.sentiment else "Take Your Time"
        requires_human = email.sentiment.requires_human if email.sentiment else False
        confidence = email.classification.confidence if email.classification else 0.0

        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO processed_emails
                   (email_id, run_id, subject, sender, date, body_preview,
                    category, sentiment, urgency_label, urgency_score,
                    requires_human, classification_confidence, processed_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                   ON CONFLICT (email_id) DO UPDATE
                   SET run_id=$2, category=$7, sentiment=$8, urgency_label=$9,
                       urgency_score=$10, requires_human=$11,
                       classification_confidence=$12, processed_at=$13""",
                email.message_id, run_id, email.subject, email.sender,
                email.date, email.snippet[:300], category, sentiment,
                urgency_label, urgency_score, requires_human, confidence,
                datetime.now(timezone.utc),
            )

    async def get_emails(
        self,
        page: int = 1,
        limit: int = 20,
        category: str | None = None,
        urgency: str | None = None,
        search: str | None = None,
    ) -> tuple[list[ProcessedEmail], int]:
        conditions: list[str] = []
        params: list[Any] = []
        p = 1

        if category:
            conditions.append(f"category = ${p}")
            params.append(category)
            p += 1
        if urgency:
            conditions.append(f"urgency_label = ${p}")
            params.append(urgency)
            p += 1
        if search:
            conditions.append(
                f"(subject ILIKE ${p} OR sender ILIKE ${p} OR body_preview ILIKE ${p})"
            )
            params.append(f"%{search}%")
            p += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        offset = (page - 1) * limit

        async with self._pool.acquire() as conn:
            total: int = await conn.fetchval(
                f"SELECT COUNT(*) FROM processed_emails {where}", *params
            )
            rows = await conn.fetch(
                f"""SELECT pe.*,
                       (SELECT COUNT(*) FROM draft_replies dr WHERE dr.email_id=pe.email_id) has_draft,
                       (SELECT COUNT(*) FROM action_items ai
                        WHERE ai.email_id=pe.email_id AND ai.completed=FALSE) action_count
                    FROM processed_emails pe {where}
                    ORDER BY urgency_score DESC, processed_at DESC
                    LIMIT ${p} OFFSET ${p + 1}""",
                *params, limit, offset,
            )

        return [_row_to_email(r) for r in rows], total or 0

    async def get_email_by_id(self, email_id: str) -> ProcessedEmail | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT pe.*,
                       (SELECT COUNT(*) FROM draft_replies dr WHERE dr.email_id=pe.email_id) has_draft,
                       (SELECT COUNT(*) FROM action_items ai
                        WHERE ai.email_id=pe.email_id AND ai.completed=FALSE) action_count
                   FROM processed_emails pe WHERE pe.email_id=$1""",
                email_id,
            )
        return _row_to_email(row) if row else None

    async def get_priority_inbox(self, limit: int = 50) -> list[ProcessedEmail]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT pe.*,
                       (SELECT COUNT(*) FROM draft_replies dr WHERE dr.email_id=pe.email_id) has_draft,
                       (SELECT COUNT(*) FROM action_items ai
                        WHERE ai.email_id=pe.email_id AND ai.completed=FALSE) action_count
                   FROM processed_emails pe
                   WHERE pe.urgency_score > 0.3
                   ORDER BY pe.urgency_score DESC, pe.processed_at DESC
                   LIMIT $1""",
                limit,
            )
        return [_row_to_email(r) for r in rows]

    # ── draft replies ─────────────────────────────────────────────────────────

    async def save_draft(self, draft: DraftReply) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO draft_replies
                   (id, email_id, run_id, subject, sender, draft_content, tone, generated_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                   ON CONFLICT (id) DO UPDATE
                   SET draft_content=$6, tone=$7, generated_at=$8""",
                draft.id, draft.email_id, draft.run_id, draft.subject,
                draft.sender, draft.draft_content, draft.tone, draft.generated_at,
            )

    async def get_draft(self, email_id: str) -> DraftReply | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM draft_replies WHERE email_id=$1 ORDER BY generated_at DESC LIMIT 1",
                email_id,
            )
        if not row:
            return None
        return DraftReply(
            id=row["id"],
            email_id=row["email_id"],
            run_id=row["run_id"] or "",
            subject=row["subject"] or "",
            sender=row["sender"] or "",
            draft_content=row["draft_content"],
            tone=row["tone"] or "professional",
            generated_at=row["generated_at"],
        )

    async def list_drafts(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT dr.*, pe.urgency_score, pe.category, pe.urgency_label
                   FROM draft_replies dr
                   LEFT JOIN processed_emails pe ON dr.email_id = pe.email_id
                   ORDER BY dr.generated_at DESC LIMIT $1""",
                limit,
            )
        return [dict(r) for r in rows]

    # ── action items ──────────────────────────────────────────────────────────

    async def save_action_items(self, items: list[ActionItem]) -> None:
        if not items:
            return
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for item in items:
                    await conn.execute(
                        """INSERT INTO action_items
                           (id, email_id, run_id, task, priority, due_date, completed, created_at)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                           ON CONFLICT (id) DO NOTHING""",
                        item.id, item.email_id, item.run_id, item.task,
                        item.priority.value, item.due_date, item.completed, item.created_at,
                    )

    async def get_action_items(
        self,
        completed: bool | None = None,
        priority: str | None = None,
        run_id: str | None = None,
    ) -> list[ActionItem]:
        conditions: list[str] = []
        params: list[Any] = []
        p = 1

        if completed is not None:
            conditions.append(f"completed = ${p}")
            params.append(completed)
            p += 1
        if priority:
            conditions.append(f"priority = ${p}")
            params.append(priority)
            p += 1
        if run_id:
            conditions.append(f"run_id = ${p}")
            params.append(run_id)
            p += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM action_items {where} "
                "ORDER BY CASE priority WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END,"
                " created_at DESC",
                *params,
            )
        return [
            ActionItem(
                id=r["id"],
                email_id=r["email_id"],
                run_id=r["run_id"] or "",
                task=r["task"],
                priority=ActionItemPriority(r["priority"]),
                due_date=r["due_date"],
                completed=bool(r["completed"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def toggle_action_item(self, item_id: str) -> bool:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE action_items SET completed = NOT completed WHERE id=$1", item_id
            )
            val = await conn.fetchval(
                "SELECT completed FROM action_items WHERE id=$1", item_id
            )
        return bool(val)

    async def delete_action_item(self, item_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM action_items WHERE id=$1", item_id)

    async def delete_completed_actions(self) -> int:
        async with self._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM action_items WHERE completed=TRUE"
            )
            await conn.execute("DELETE FROM action_items WHERE completed=TRUE")
        return count or 0

    # ── schedule ──────────────────────────────────────────────────────────────

    async def get_schedule(self) -> ScheduleConfig:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM schedule_config WHERE id=1")
        if not row:
            return ScheduleConfig()
        return ScheduleConfig(
            enabled=bool(row["enabled"]),
            schedule_type=ScheduleType(row["schedule_type"]),
            interval_hours=row["interval_hours"],
            cron_hour=row["cron_hour"],
            cron_minute=row["cron_minute"],
            max_emails=row["max_emails"],
            generate_report=bool(row["generate_report"]),
            next_run=row["next_run"],
            last_run=row["last_run"],
        )

    async def save_schedule(self, config: ScheduleConfig) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO schedule_config
                   (id, enabled, schedule_type, interval_hours, cron_hour, cron_minute,
                    max_emails, generate_report, next_run, last_run)
                   VALUES (1,$1,$2,$3,$4,$5,$6,$7,$8,$9)
                   ON CONFLICT (id) DO UPDATE
                   SET enabled=$1, schedule_type=$2, interval_hours=$3,
                       cron_hour=$4, cron_minute=$5, max_emails=$6,
                       generate_report=$7, next_run=$8, last_run=$9""",
                config.enabled, config.schedule_type.value,
                config.interval_hours, config.cron_hour, config.cron_minute,
                config.max_emails, config.generate_report,
                config.next_run, config.last_run,
            )

    # ── user settings ─────────────────────────────────────────────────────────

    async def get_settings(self) -> UserSettings:
        async with self._pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT settings_json FROM user_settings WHERE id=1"
            )
        if not val:
            return UserSettings()
        try:
            return UserSettings(**json.loads(val))
        except Exception:
            return UserSettings()

    async def save_settings(self, settings: UserSettings) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO user_settings (id, settings_json) VALUES (1,$1)
                   ON CONFLICT (id) DO UPDATE SET settings_json=$1""",
                settings.model_dump_json(),
            )

    # ── contact intelligence ──────────────────────────────────────────────────

    async def get_contacts(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT
                       sender,
                       COUNT(*) AS email_count,
                       ROUND(AVG(urgency_score)::numeric, 3) AS avg_urgency,
                       SUM(CASE WHEN requires_human THEN 1 ELSE 0 END) AS human_needed,
                       SUM(CASE WHEN category='URGENT' THEN 1 ELSE 0 END) AS urgent_count,
                       MAX(processed_at) AS last_seen
                   FROM processed_emails
                   GROUP BY sender
                   ORDER BY email_count DESC
                   LIMIT $1""",
                limit,
            )
        return [dict(r) for r in rows]

    # ── anomaly detection ─────────────────────────────────────────────────────

    async def get_anomalies(self) -> dict[str, Any]:
        day_cut = datetime.now(timezone.utc) - timedelta(days=1)
        week_cut = datetime.now(timezone.utc) - timedelta(days=7)

        async with self._pool.acquire() as conn:
            recent = await conn.fetchrow(
                """SELECT COUNT(*) total, AVG(urgency_score) avg_urg,
                          SUM(CASE WHEN requires_human THEN 1 ELSE 0 END) human_count
                   FROM processed_emails WHERE processed_at >= $1""",
                day_cut,
            )
            baseline = await conn.fetchrow(
                """SELECT COUNT(*) / 7.0 daily_avg, AVG(urgency_score) avg_urg
                   FROM processed_emails WHERE processed_at >= $1""",
                week_cut,
            )
            top_sender = await conn.fetchrow(
                """SELECT sender, COUNT(*) c FROM processed_emails
                   WHERE processed_at >= $1
                   GROUP BY sender ORDER BY c DESC LIMIT 1""",
                day_cut,
            )

        anomalies = []
        r_total = recent["total"] or 0
        b_avg = float(baseline["daily_avg"] or 0)
        r_urg = float(recent["avg_urg"] or 0)
        b_urg = float(baseline["avg_urg"] or 0)

        if b_avg > 0 and r_total > b_avg * 2:
            anomalies.append({
                "type": "volume_spike",
                "severity": "warning",
                "message": f"Email volume 2x higher than usual ({r_total} vs avg {round(b_avg,1)}/day)",
            })
        if b_urg > 0 and r_urg > b_urg * 1.5:
            anomalies.append({
                "type": "urgency_spike",
                "severity": "critical",
                "message": f"Urgency score spiked ({round(r_urg,2)} vs baseline {round(b_urg,2)})",
            })
        human_count = recent["human_count"] or 0
        if human_count > 3:
            anomalies.append({
                "type": "high_human_required",
                "severity": "warning",
                "message": f"{human_count} emails need personal responses today",
            })

        return {
            "anomalies": anomalies,
            "recent_24h": {
                "total": r_total,
                "avg_urgency": round(r_urg, 3),
                "human_needed": human_count,
            },
            "baseline_daily": {"avg_emails": round(b_avg, 1), "avg_urgency": round(b_urg, 3)},
            "top_sender_today": dict(top_sender) if top_sender and top_sender["c"] else None,
        }

    # ── follow-ups ────────────────────────────────────────────────────────────

    async def add_follow_up(self, follow_up: Any) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO follow_ups
                   (id, email_id, subject, sender, follow_up_date, note, completed, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                follow_up.id, follow_up.email_id, follow_up.subject,
                follow_up.sender, follow_up.follow_up_date,
                follow_up.note, follow_up.completed, follow_up.created_at,
            )

    async def get_follow_ups(self, completed: bool | None = None) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            if completed is not None:
                rows = await conn.fetch(
                    "SELECT * FROM follow_ups WHERE completed=$1"
                    " ORDER BY follow_up_date ASC, completed ASC",
                    completed,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM follow_ups ORDER BY follow_up_date ASC, completed ASC"
                )
        return [dict(r) for r in rows]

    async def toggle_follow_up(self, item_id: str) -> bool:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE follow_ups SET completed = NOT completed WHERE id=$1", item_id
            )
            val = await conn.fetchval(
                "SELECT completed FROM follow_ups WHERE id=$1", item_id
            )
        return bool(val)

    async def delete_follow_up(self, item_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM follow_ups WHERE id=$1", item_id)

    # ── translations ──────────────────────────────────────────────────────────

    async def save_translation(
        self,
        email_id: str,
        language: str,
        translated_subject: str,
        translated_body: str,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO email_translations
                   (email_id, original_language, translated_subject, translated_body, translated_at)
                   VALUES ($1,$2,$3,$4,$5)
                   ON CONFLICT (email_id) DO UPDATE
                   SET original_language=$2, translated_subject=$3,
                       translated_body=$4, translated_at=$5""",
                email_id, language, translated_subject, translated_body,
                datetime.now(timezone.utc),
            )

    async def get_translation(self, email_id: str) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM email_translations WHERE email_id=$1", email_id
            )
        return dict(row) if row else None

    # ── briefing cache ────────────────────────────────────────────────────────

    async def get_briefing_cache(self) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM briefing_cache WHERE id=1")
        return dict(row) if row else None

    async def save_briefing_cache(self, content: str, email_count: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO briefing_cache (id, content, generated_at, email_count)
                   VALUES (1,$1,$2,$3)
                   ON CONFLICT (id) DO UPDATE
                   SET content=$1, generated_at=$2, email_count=$3""",
                content, datetime.now(timezone.utc), email_count,
            )

    # ── export ────────────────────────────────────────────────────────────────

    async def export_emails_csv(self, days: int = 30) -> str:
        cut = _cutoff(days)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT email_id, subject, sender, date, category, sentiment,
                          urgency_label, urgency_score, requires_human, processed_at
                   FROM processed_emails
                   WHERE processed_at >= $1
                   ORDER BY urgency_score DESC, processed_at DESC""",
                cut,
            )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Email ID", "Subject", "Sender", "Date", "Category",
            "Sentiment", "Urgency Label", "Urgency Score", "Requires Human", "Processed At",
        ])
        for r in rows:
            writer.writerow([
                r["email_id"], r["subject"], r["sender"], r["date"],
                r["category"], r["sentiment"], r["urgency_label"],
                round(r["urgency_score"] or 0.0, 3),
                "Yes" if r["requires_human"] else "No",
                r["processed_at"].isoformat() if r["processed_at"] else "",
            ])
        return output.getvalue()


# ── singleton ─────────────────────────────────────────────────────────────────

_store: StateStore | None = None


def get_state_store() -> StateStore:
    global _store
    if _store is None:
        _store = StateStore()
    return _store
