from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class EmailCategory(StrEnum):
    URGENT = "URGENT"
    CUSTOMER_INQUIRY = "CUSTOMER_INQUIRY"
    INVOICE = "INVOICE"
    NEWSLETTER = "NEWSLETTER"
    SPAM = "SPAM"
    GENERAL = "GENERAL"


class Sentiment(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


class WorkflowStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class UrgencyLabel(StrEnum):
    IMPORTANT = "Important"
    REVIEW = "Needed Review"
    LOW = "Take Your Time"

    @classmethod
    def from_score(cls, score: float) -> UrgencyLabel:
        if score >= 0.7:
            return cls.IMPORTANT
        if score >= 0.4:
            return cls.REVIEW
        return cls.LOW


class ActionItemPriority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ScheduleType(StrEnum):
    DAILY = "daily"
    INTERVAL = "interval"


# ── Core email models ─────────────────────────────────────────────────────────

class EmailClassification(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: EmailCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class SentimentAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    sentiment: Sentiment
    urgency_score: float = Field(ge=0.0, le=1.0)
    requires_human: bool
    confidence: float = Field(ge=0.0, le=1.0)

    @property
    def urgency_label(self) -> UrgencyLabel:
        return UrgencyLabel.from_score(self.urgency_score)


class EmailData(BaseModel):
    message_id: str
    subject: str
    sender: str
    recipient: str
    date: str
    body: str
    snippet: str
    classification: EmailClassification | None = None
    sentiment: SentimentAnalysis | None = None


class SheetRow(BaseModel):
    email_id: str
    subject: str
    sender: str
    date: str
    summary: str
    category: str = "GENERAL"
    sentiment: str = "NEUTRAL"
    urgency_label: str = "Take Your Time"
    processed_at: str


class ReportData(BaseModel):
    title: str
    summary: str
    insights: list[str]
    urgency_stats: dict[str, int] = Field(default_factory=dict)
    priority_emails: list[str] = Field(default_factory=list)
    email_count: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_used: str = "gpt-4o-mini"
    cached_tokens: int = 0


class StepLog(BaseModel):
    step_name: str
    status: StepStatus = StepStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    retry_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowRun(BaseModel):
    run_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    error_message: str | None = None
    steps: list[StepLog] = Field(default_factory=list)
    emails_processed: int = 0
    report_path: str | None = None


class WorkflowTriggerRequest(BaseModel):
    max_emails: int = Field(default=10, ge=1, le=100)
    generate_report: bool = Field(default=True)


class WorkflowRunResponse(BaseModel):
    run_id: str
    status: WorkflowStatus
    message: str
    ws_url: str = ""


# ── New feature models ────────────────────────────────────────────────────────

class DraftReply(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    email_id: str
    run_id: str = ""
    subject: str = ""
    sender: str = ""
    draft_content: str
    tone: str = "professional"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ActionItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    email_id: str
    run_id: str = ""
    task: str
    priority: ActionItemPriority = ActionItemPriority.MEDIUM
    due_date: str | None = None
    completed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScheduleConfig(BaseModel):
    enabled: bool = False
    schedule_type: ScheduleType = ScheduleType.DAILY
    interval_hours: int = Field(6, ge=1, le=168)
    cron_hour: int = Field(9, ge=0, le=23)
    cron_minute: int = Field(0, ge=0, le=59)
    max_emails: int = Field(10, ge=1, le=100)
    generate_report: bool = True
    next_run: datetime | None = None
    last_run: datetime | None = None


class UserSettings(BaseModel):
    auto_draft_enabled: bool = True
    action_items_enabled: bool = True
    default_max_emails: int = Field(10, ge=1, le=100)
    default_generate_report: bool = True
    email_query_filter: str = ""
    notify_urgent: bool = True
    notify_complete: bool = True


class ProcessedEmail(BaseModel):
    email_id: str
    run_id: str = ""
    subject: str
    sender: str
    date: str
    body_preview: str = ""
    category: str = "GENERAL"
    sentiment: str = "NEUTRAL"
    urgency_label: str = "Take Your Time"
    urgency_score: float = 0.0
    requires_human: bool = False
    classification_confidence: float = 0.0
    processed_at: str = ""
    has_draft: bool = False
    action_count: int = 0


class FollowUp(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    email_id: str = ""
    subject: str = ""
    sender: str = ""
    follow_up_date: str
    note: str = ""
    completed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ComposeRequest(BaseModel):
    to: str
    intent: str
    tone: str = "professional"
    context: str = ""
    thread_context: str = ""
