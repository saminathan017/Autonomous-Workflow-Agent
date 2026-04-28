from __future__ import annotations

from loguru import logger

from autonomous_workflow_agent.app.ai.openai_client import get_openai_client

_COMPOSE_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "compose_email",
            "description": "Compose a complete, polished email based on the user's intent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Email subject line — concise and specific",
                    },
                    "body": {
                        "type": "string",
                        "description": "Full email body including greeting, content paragraphs, and sign-off as [Your Name]",
                    },
                    "suggested_tone_notes": {
                        "type": "string",
                        "description": "Brief note on tone/style used",
                    },
                },
                "required": ["subject", "body"],
            },
        },
    }
]

_TONE_DESCRIPTIONS = {
    "professional": "formal, respectful, business-appropriate",
    "friendly": "warm, approachable, conversational but professional",
    "direct": "concise, no fluff, get straight to the point",
    "persuasive": "compelling, builds case with evidence, confident",
    "apologetic": "empathetic, acknowledges the issue, solution-focused",
    "formal": "highly formal, traditional business letter style",
}

_SYSTEM = """You are an expert email writer. Compose a complete, professional email.

Requirements:
- The email must directly address the stated intent
- Match the specified tone precisely
- Be specific — no vague filler content
- Include: appropriate greeting, clear body, professional sign-off as [Your Name]
- Subject line should be clear and relevant
- Length: appropriate for the content (typically 80-200 words for body)"""


async def compose_email(
    to: str,
    intent: str,
    tone: str = "professional",
    context: str = "",
    thread_context: str = "",
) -> dict | None:
    client = get_openai_client()
    tone_desc = _TONE_DESCRIPTIONS.get(tone, tone)

    parts = [
        f"Compose an email to: {to}",
        f"Intent: {intent}",
        f"Tone: {tone} ({tone_desc})",
    ]
    if context:
        parts.append(f"Additional context: {context}")
    if thread_context:
        parts.append(f"Reply context (previous email): {thread_context[:600]}")

    result = await client.complete(
        system=_SYSTEM,
        user="\n".join(parts),
        tools=_COMPOSE_TOOL,
        tool_choice={"type": "function", "function": {"name": "compose_email"}},
        max_tokens=700,
    )

    if not result.success or not result.tool_result:
        logger.warning(f"Email composition failed: {result.error}")
        return None

    inp = result.tool_result["input"]
    return {
        "subject": inp.get("subject", ""),
        "body": inp.get("body", ""),
        "to": to,
        "tone": tone,
        "tone_notes": inp.get("suggested_tone_notes", ""),
    }
