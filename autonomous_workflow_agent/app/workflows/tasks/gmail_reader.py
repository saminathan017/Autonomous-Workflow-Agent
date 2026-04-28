from __future__ import annotations

import asyncio
import base64
from functools import partial
from typing import Any

from googleapiclient.errors import HttpError
from loguru import logger

from autonomous_workflow_agent.app.ai.email_classifier import classify_email
from autonomous_workflow_agent.app.ai.sentiment_analyzer import analyze_sentiment
from autonomous_workflow_agent.app.auth.google_oauth import get_auth_manager
from autonomous_workflow_agent.app.workflows.models import EmailData


def _decode_body(payload: dict[str, Any]) -> str:
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    data = payload.get("body", {}).get("data")
    if data:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return ""


def _parse_message(message: dict[str, Any]) -> EmailData | None:
    try:
        headers = {h["name"]: h["value"] for h in message["payload"]["headers"]}
        return EmailData(
            message_id=message["id"],
            subject=headers.get("Subject", "(No Subject)"),
            sender=headers.get("From", "Unknown"),
            recipient=headers.get("To", "Unknown"),
            date=headers.get("Date", ""),
            body=_decode_body(message["payload"]),
            snippet=message.get("snippet", ""),
        )
    except Exception as exc:
        logger.warning(f"Failed to parse message {message.get('id')}: {exc}")
        return None


class GmailReader:
    """
    Async Gmail reader — wraps synchronous Google API calls in a thread-pool
    executor so they never block the event loop. AI analysis runs concurrently
    via asyncio.gather for maximum throughput.
    """

    def __init__(self) -> None:
        self._auth = get_auth_manager()
        self._service: Any = None

    def _ensure_service(self) -> bool:
        if not self._service:
            self._service = self._auth.get_gmail_service()
        return self._service is not None

    async def _run_sync(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

    async def _analyse(self, email: EmailData) -> EmailData:
        classification, sentiment = await asyncio.gather(
            classify_email(email),
            analyze_sentiment(email),
        )
        return email.model_copy(
            update={"classification": classification, "sentiment": sentiment}
        )

    async def fetch_emails(
        self, max_results: int = 10, query: str = ""
    ) -> list[EmailData]:
        if not self._ensure_service():
            logger.error("Gmail service unavailable — run authenticate.py first")
            return []

        try:
            list_req = self._service.users().messages().list(
                userId="me", maxResults=max_results, q=query
            )
            results = await self._run_sync(list_req.execute)
            messages = results.get("messages", [])
            logger.info(f"Gmail: found {len(messages)} messages")

            raw_emails: list[EmailData] = []
            for msg in messages:
                try:
                    get_req = self._service.users().messages().get(
                        userId="me", id=msg["id"], format="full"
                    )
                    full = await self._run_sync(get_req.execute)
                    parsed = _parse_message(full)
                    if parsed:
                        raw_emails.append(parsed)
                except HttpError as exc:
                    logger.warning(f"Could not fetch message {msg['id']}: {exc}")

            # Concurrent AI analysis — one gather per email
            analysed = await asyncio.gather(
                *[self._analyse(e) for e in raw_emails], return_exceptions=True
            )
            emails: list[EmailData] = []
            for item in analysed:
                if isinstance(item, Exception):
                    logger.warning(f"AI analysis error: {item}")
                else:
                    emails.append(item)

            logger.info(f"Gmail: processed {len(emails)} emails with AI analysis")
            return emails

        except HttpError as exc:
            logger.error(f"Gmail API error: {exc}")
            return []
        except Exception as exc:
            logger.error(f"Unexpected error in GmailReader: {exc}")
            return []


def get_gmail_reader() -> GmailReader:
    return GmailReader()
