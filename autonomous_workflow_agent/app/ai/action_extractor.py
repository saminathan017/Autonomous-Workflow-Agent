from __future__ import annotations

from loguru import logger

from autonomous_workflow_agent.app.ai.openai_client import get_openai_client
from autonomous_workflow_agent.app.workflows.models import (
    ActionItem,
    ActionItemPriority,
    EmailCategory,
    EmailData,
)

_SKIP_CATEGORIES = {EmailCategory.NEWSLETTER, EmailCategory.SPAM}

_EXTRACT_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "extract_action_items",
            "description": "Extract all concrete action items, tasks, and follow-ups the email reader must act on.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "List of action items. Empty array if none found.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "task": {
                                    "type": "string",
                                    "description": "Clear, actionable task description",
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["HIGH", "MEDIUM", "LOW"],
                                    "description": "HIGH=urgent/time-sensitive, MEDIUM=important, LOW=nice-to-have",
                                },
                                "due_date": {
                                    "type": "string",
                                    "description": "Due date if mentioned (e.g. 'April 25', 'EOD Friday'), else null",
                                },
                            },
                            "required": ["task", "priority"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    }
]

_SYSTEM = """You are an assistant that extracts action items from emails.

Extract only CONCRETE tasks that require action from the reader.
Skip: general FYI statements, vague suggestions, marketing content.
Return an empty items array if no clear actions exist."""


async def extract_action_items(email: EmailData, run_id: str = "") -> list[ActionItem]:
    if email.classification and email.classification.category in _SKIP_CATEGORIES:
        return []

    client = get_openai_client()
    user_msg = (
        f"From: {email.sender}\n"
        f"Subject: {email.subject}\n\n"
        f"{email.body[:1500]}"
    )

    result = await client.complete(
        system=_SYSTEM,
        user=user_msg,
        tools=_EXTRACT_TOOL,
        tool_choice={"type": "function", "function": {"name": "extract_action_items"}},
        max_tokens=500,
    )

    if not result.success or not result.tool_result:
        logger.debug(f"No action items extracted for {email.message_id}: {result.error}")
        return []

    raw_items = result.tool_result.get("input", {}).get("items", [])
    action_items: list[ActionItem] = []
    for item in raw_items:
        try:
            action_items.append(
                ActionItem(
                    email_id=email.message_id,
                    run_id=run_id,
                    task=item["task"],
                    priority=ActionItemPriority(item.get("priority", "MEDIUM")),
                    due_date=item.get("due_date"),
                )
            )
        except Exception as exc:
            logger.warning(f"Skipping malformed action item: {exc}")

    return action_items
