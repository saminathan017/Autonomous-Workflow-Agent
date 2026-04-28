from __future__ import annotations

from loguru import logger

from autonomous_workflow_agent.app.ai.openai_client import get_openai_client

_CLUSTER_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "cluster_email_topics",
            "description": "Group emails into meaningful topic clusters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Short, descriptive topic name (2-5 words)",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "1-2 sentence description of what this topic covers",
                                },
                                "count": {
                                    "type": "integer",
                                    "description": "Approximate number of emails in this cluster",
                                },
                                "key_senders": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Up to 3 key senders in this cluster",
                                },
                                "urgency": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                    "description": "Overall urgency level of this topic cluster",
                                },
                                "sample_subjects": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "2-3 representative email subjects",
                                },
                            },
                            "required": ["name", "description", "count", "urgency", "sample_subjects"],
                        },
                    }
                },
                "required": ["topics"],
            },
        },
    }
]

_SYSTEM = """You are an expert at analysing email patterns.
Group the provided emails into 4-8 meaningful topic clusters.
Each cluster should represent a real recurring theme or project.
Focus on actionable groupings, not arbitrary categories."""


async def cluster_topics(emails: list[dict], max_topics: int = 8) -> list[dict]:
    if not emails:
        return []

    client = get_openai_client()
    lines = [f"Total emails: {len(emails)}\n"]
    for e in emails[:60]:
        lines.append(
            f"- {e.get('subject', '?')[:70]} | {e.get('sender', '?')[:35]} "
            f"| {e.get('category', '?')}"
        )

    result = await client.complete(
        system=_SYSTEM,
        user=f"Identify up to {max_topics} topic clusters from these emails:\n\n" + "\n".join(lines),
        tools=_CLUSTER_TOOL,
        tool_choice={"type": "function", "function": {"name": "cluster_email_topics"}},
        max_tokens=800,
    )

    if not result.success or not result.tool_result:
        logger.warning(f"Topic clustering failed: {result.error}")
        return []

    return result.tool_result["input"].get("topics", [])
