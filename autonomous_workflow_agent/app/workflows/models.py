"""
Pydantic models for workflow data structures.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class EmailCategory(str, Enum):
    """Email classification categories."""
    URGENT = "urgent"
    CUSTOMER_INQUIRY = "customer_inquiry"
    INVOICE = "invoice"
    NEWSLETTER = "newsletter"
    SPAM = "spam"
    GENERAL = "general"


class Sentiment(str, Enum):
    """Email sentiment types."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(str, Enum):
    """Individual step execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EmailClassification(BaseModel):
    """Email classification result."""
    category: EmailCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class SentimentAnalysis(BaseModel):
    """Email sentiment analysis result."""
    sentiment: Sentiment
    urgency_score: float = Field(ge=0.0, le=1.0, description="0=low urgency, 1=high urgency")
    requires_human: bool
    confidence: float = Field(ge=0.0, le=1.0)


class EmailData(BaseModel):
    """Structured email data."""
    message_id: str
    subject: str
    sender: str
    recipient: str
    date: datetime
    body: str
    snippet: str
    classification: Optional[EmailClassification] = None
    sentiment: Optional[SentimentAnalysis] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SheetRow(BaseModel):
    """Data row for Google Sheets."""
    email_id: str
    subject: str
    sender: str
    date: str
    summary: str
    category: str = "general"
    sentiment: str = "neutral"
    urgency_score: float = 0.0
    processed_at: str


class ReportData(BaseModel):
    """AI-generated report data."""
    title: str
    summary: str
    insights: List[str]
    urgency_stats: Dict[str, int] = Field(default_factory=dict)
    priority_emails: List[str] = Field(default_factory=list)
    email_count: int
    generated_at: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class StepLog(BaseModel):
    """Log entry for a workflow step."""
    step_name: str
    status: StepStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class WorkflowRun(BaseModel):
    """Complete workflow run data."""
    run_id: str
    status: WorkflowStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    steps: List[StepLog] = Field(default_factory=list)
    emails_processed: int = 0
    report_path: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class WorkflowTriggerRequest(BaseModel):
    """Request to trigger a workflow."""
    max_emails: int = Field(default=10, ge=1, le=100, description="Maximum emails to process")
    generate_report: bool = Field(default=True, description="Whether to generate AI report")


class WorkflowRunResponse(BaseModel):
    """Response after triggering a workflow."""
    run_id: str
    status: WorkflowStatus
    message: str
