from __future__ import annotations

from loguru import logger

from autonomous_workflow_agent.app.ai.openai_client import get_openai_client
from autonomous_workflow_agent.app.workflows.models import (
    DraftReply,
    EmailCategory,
    EmailData,
)

_TONE_MAP: dict[str, str] = {
    EmailCategory.CUSTOMER_INQUIRY: "helpful, warm and solution-focused",
    EmailCategory.URGENT: "prompt, empathetic and clearly action-oriented",
    EmailCategory.INVOICE: "formal, professional and precise",
    EmailCategory.GENERAL: "professional and concise",
    EmailCategory.NEWSLETTER: "brief and appreciative",
}

_SYSTEM = """You are a professional email assistant writing reply drafts.

Rules:
- Write only the email body — no subject line, no meta-commentary
- Match the specified tone exactly
- Be specific and concrete, referencing the original email's content
- Keep it under 120 words
- Use an appropriate greeting (Dear / Hi / Hello based on tone)
- Sign off as "[Your Name]"
- Do not include placeholder text like [Company] — write naturally"""


async def generate_draft_reply(email: EmailData, run_id: str = "") -> DraftReply | None:
    client = get_openai_client()
    category = email.classification.category if email.classification else EmailCategory.GENERAL
    tone = _TONE_MAP.get(str(category), "professional and concise")

    user_msg = (
        f"From: {email.sender}\n"
        f"Subject: {email.subject}\n\n"
        f"Email body:\n{email.body[:1200]}\n\n"
        f"Required tone: {tone}\n\n"
        "Write a reply draft:"
    )

    result = await client.complete(system=_SYSTEM, user=user_msg, max_tokens=300)
    if not result.success or not result.content:
        logger.warning(f"Draft generation failed for {email.message_id}: {result.error}")
        return None

    return DraftReply(
        email_id=email.message_id,
        run_id=run_id,
        subject=f"Re: {email.subject}",
        sender=email.sender,
        draft_content=result.content.strip(),
        tone=tone,
    )
