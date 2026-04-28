from __future__ import annotations

from loguru import logger

from autonomous_workflow_agent.app.ai.openai_client import get_openai_client

_SYSTEM = """You are a sharp executive assistant delivering a morning email intelligence briefing.

Your briefing format:
## Situation Overview
2-3 sentences on overall inbox state.

## Urgent — Needs Action Now
Bullet points for any critical items requiring immediate response. Skip if none.

## Key Themes This Period
3-5 bullet points of the main topics/projects appearing across emails.

## Recommended Next Steps
3 prioritised actions the reader should take today.

## At a Glance
Quick stats line.

Rules:
- Be specific, name subjects/senders when relevant
- Skip sections that have nothing meaningful to say
- Keep entire briefing under 500 words
- Use bold for names/deadlines
- Write as if briefing a busy executive"""


async def generate_briefing(emails: list[dict], period_days: int = 7) -> str:
    if not emails:
        return "## No Data\n\nNo processed emails found. Run a workflow to populate your inbox."

    client = get_openai_client()

    urgent = [e for e in emails if e.get("urgency_label") == "Important"]
    review = [e for e in emails if e.get("urgency_label") == "Needed Review"]

    lines = [f"Period: last {period_days} days — {len(emails)} total emails processed\n"]
    lines.append(
        f"Urgent: {len(urgent)} | Review needed: {len(review)} | "
        f"Routine: {len(emails) - len(urgent) - len(review)}\n"
    )
    lines.append("Email list (subject | sender | category | urgency):")

    for e in emails[:40]:
        lines.append(
            f"- {e.get('subject', '?')[:80]} | {e.get('sender', '?')[:40]} "
            f"| {e.get('category', '?')} | {e.get('urgency_label', '?')}"
        )
        if e.get("body_preview"):
            lines.append(f"  > {e['body_preview'][:120]}")

    result = await client.complete(
        system=_SYSTEM,
        user="\n".join(lines),
        max_tokens=900,
    )

    if not result.success:
        logger.warning(f"Briefing generation failed: {result.error}")
        return "## Briefing Unavailable\n\nFailed to generate briefing. Check your OPENAI_API_KEY."

    return result.content.strip()
