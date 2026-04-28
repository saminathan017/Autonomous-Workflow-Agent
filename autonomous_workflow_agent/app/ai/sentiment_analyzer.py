from __future__ import annotations

from loguru import logger

from autonomous_workflow_agent.app.ai.openai_client import get_openai_client
from autonomous_workflow_agent.app.workflows.models import (
    EmailData,
    Sentiment,
    SentimentAnalysis,
)

_SYSTEM_PROMPT = """\
You are an expert email sentiment and urgency analyst for a professional workflow system.
Evaluate the emotional tone, urgency level, and whether the email needs immediate human attention.
Be precise — urgency_score must reflect actual time sensitivity, not just negative tone."""

_ANALYZE_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "analyze_sentiment",
            "description": "Analyse email sentiment, urgency, and whether human review is needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sentiment": {
                        "type": "string",
                        "enum": ["POSITIVE", "NEGATIVE", "NEUTRAL"],
                        "description": "Overall emotional tone of the email.",
                    },
                    "urgency_score": {
                        "type": "number",
                        "description": "0 = no urgency, 1 = requires immediate action.",
                    },
                    "requires_human": {
                        "type": "boolean",
                        "description": "True if this email demands immediate human attention.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Model confidence in this analysis (0 to 1).",
                    },
                },
                "required": ["sentiment", "urgency_score", "requires_human", "confidence"],
            },
        },
    }
]

_POSITIVE_WORDS = frozenset(
    {"thank", "great", "excellent", "appreciate", "wonderful", "perfect", "love", "happy"}
)
_NEGATIVE_WORDS = frozenset(
    {"urgent", "problem", "issue", "error", "complaint", "broken", "failed", "critical", "angry"}
)
_URGENCY_WORDS = frozenset(
    {"urgent", "asap", "immediately", "critical", "emergency", "deadline", "overdue"}
)


async def analyze_sentiment(email: EmailData) -> SentimentAnalysis:
    client = get_openai_client()
    user_msg = (
        f"Subject: {email.subject}\n"
        f"From: {email.sender}\n"
        f"Content: {email.snippet[:400]}\n\n"
        "Analyse sentiment and urgency."
    )

    result = await client.complete(
        system=_SYSTEM_PROMPT,
        user=user_msg,
        tools=_ANALYZE_TOOL,
        tool_choice={"type": "function", "function": {"name": "analyze_sentiment"}},
        max_tokens=256,
    )

    if result.success and result.tool_result:
        data = result.tool_result["input"]
        return SentimentAnalysis(
            sentiment=Sentiment(data["sentiment"]),
            urgency_score=float(data["urgency_score"]),
            requires_human=bool(data["requires_human"]),
            confidence=float(data["confidence"]),
        )

    logger.warning(f"OpenAI sentiment unavailable ({result.error}); using keyword fallback")
    return _keyword_analyze(email)


def _keyword_analyze(email: EmailData) -> SentimentAnalysis:
    words = set(f"{email.subject} {email.snippet}".lower().split())
    pos = len(words & _POSITIVE_WORDS)
    neg = len(words & _NEGATIVE_WORDS)
    urg = len(words & _URGENCY_WORDS)

    urgency_score = min(urg * 0.3, 1.0)
    if pos > neg:
        sentiment = Sentiment.POSITIVE
    elif neg > 0:
        sentiment = Sentiment.NEGATIVE
    else:
        sentiment = Sentiment.NEUTRAL

    return SentimentAnalysis(
        sentiment=sentiment,
        urgency_score=urgency_score,
        requires_human=urgency_score >= 0.6,
        confidence=0.55,
    )


class SentimentAnalyzer:
    async def analyze(self, email: EmailData) -> SentimentAnalysis:
        return await analyze_sentiment(email)


def get_sentiment_analyzer() -> SentimentAnalyzer:
    return SentimentAnalyzer()
