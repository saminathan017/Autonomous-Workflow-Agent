from __future__ import annotations

from loguru import logger

from autonomous_workflow_agent.app.ai.openai_client import get_openai_client
from autonomous_workflow_agent.app.workflows.models import (
    EmailCategory,
    EmailClassification,
    EmailData,
)

_SYSTEM_PROMPT = """\
You are an expert email classifier for a professional workflow system.
Analyse the email precisely and classify it into exactly one of the available categories.
Be concise in your reasoning — one sentence maximum."""

_CLASSIFY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "classify_email",
            "description": "Classify an email into a category with a confidence score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [c.value for c in EmailCategory],
                        "description": "The single best-fit category for this email.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence score between 0 and 1.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "One-sentence rationale for the classification.",
                    },
                },
                "required": ["category", "confidence", "reasoning"],
            },
        },
    }
]

_FALLBACK_RULES: list[tuple[EmailCategory, list[str]]] = [
    (EmailCategory.URGENT, ["urgent", "asap", "immediate", "critical", "emergency"]),
    (EmailCategory.INVOICE, ["invoice", "payment", "bill", "receipt", "due date"]),
    (EmailCategory.NEWSLETTER, ["unsubscribe", "newsletter", "digest", "promotion"]),
    (EmailCategory.SPAM, ["winner", "lottery", "free money", "click here", "limited offer"]),
    (EmailCategory.CUSTOMER_INQUIRY, ["question", "help", "support", "inquiry", "how do i"]),
]


async def classify_email(email: EmailData) -> EmailClassification:
    client = get_openai_client()
    user_msg = (
        f"Subject: {email.subject}\n"
        f"From: {email.sender}\n"
        f"Preview: {email.snippet[:400]}\n\n"
        "Classify this email."
    )

    result = await client.complete(
        system=_SYSTEM_PROMPT,
        user=user_msg,
        tools=_CLASSIFY_TOOL,
        tool_choice={"type": "function", "function": {"name": "classify_email"}},
        max_tokens=256,
    )

    if result.success and result.tool_result:
        data = result.tool_result["input"]
        return EmailClassification(
            category=EmailCategory(data["category"]),
            confidence=float(data["confidence"]),
            reasoning=data["reasoning"],
        )

    logger.warning(f"OpenAI classification unavailable ({result.error}); using keyword fallback")
    return _keyword_classify(email)


def _keyword_classify(email: EmailData) -> EmailClassification:
    text = f"{email.subject} {email.sender} {email.snippet}".lower()
    for category, keywords in _FALLBACK_RULES:
        if any(kw in text for kw in keywords):
            return EmailClassification(
                category=category,
                confidence=0.55,
                reasoning="Keyword-based fallback classification.",
            )
    return EmailClassification(
        category=EmailCategory.GENERAL,
        confidence=0.50,
        reasoning="No specific pattern matched; defaulted to GENERAL.",
    )


class EmailClassifier:
    async def classify(self, email: EmailData) -> EmailClassification:
        return await classify_email(email)


def get_email_classifier() -> EmailClassifier:
    return EmailClassifier()
