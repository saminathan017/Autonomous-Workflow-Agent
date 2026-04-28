from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from googleapiclient.errors import HttpError
from loguru import logger

from autonomous_workflow_agent.app.auth.google_oauth import get_auth_manager
from autonomous_workflow_agent.app.config import get_settings
from autonomous_workflow_agent.app.workflows.models import SheetRow

_HEADERS = [
    "Email ID", "Subject", "Sender", "Date",
    "Summary", "Category", "Sentiment", "Urgency", "Processed At",
]


class SheetsWriter:
    """
    Async Google Sheets writer with idempotency — wraps blocking API calls
    in a thread executor. Duplicate rows are detected and skipped server-side
    before any append is issued.
    """

    def __init__(self) -> None:
        self._auth = get_auth_manager()
        self._settings = get_settings()
        self._service: Any = None
        self._sheet_id = self._settings.google_sheet_id

    def _ensure_service(self) -> bool:
        if not self._service:
            self._service = self._auth.get_sheets_service()
        return self._service is not None

    async def _run_sync(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

    async def _get_existing_ids(self, sheet: str = "Sheet1") -> set[str]:
        if not self._ensure_service():
            return set()
        try:
            req = self._service.spreadsheets().values().get(
                spreadsheetId=self._sheet_id, range=f"{sheet}!A:A"
            )
            result = await self._run_sync(req.execute)
            rows = result.get("values", [])
            return {r[0] for r in rows[1:] if r}
        except HttpError as exc:
            logger.warning(f"Could not read existing IDs: {exc}")
            return set()

    async def _ensure_headers(self, sheet: str = "Sheet1") -> None:
        if not self._ensure_service():
            return
        try:
            req = self._service.spreadsheets().values().get(
                spreadsheetId=self._sheet_id, range=f"{sheet}!A1:I1"
            )
            result = await self._run_sync(req.execute)
            if not result.get("values"):
                upd = self._service.spreadsheets().values().update(
                    spreadsheetId=self._sheet_id,
                    range=f"{sheet}!A1:I1",
                    valueInputOption="RAW",
                    body={"values": [_HEADERS]},
                )
                await self._run_sync(upd.execute)
                logger.info("Sheets: headers written")
        except HttpError as exc:
            logger.warning(f"Could not ensure headers: {exc}")

    async def write_rows(self, rows: list[SheetRow], sheet: str = "Sheet1") -> int:
        if not self._ensure_service():
            logger.error("Sheets service unavailable — run authenticate.py first")
            return 0
        if not rows:
            return 0

        await self._ensure_headers(sheet)
        existing = await self._get_existing_ids(sheet)

        new_rows = [r for r in rows if r.email_id not in existing]
        if not new_rows:
            logger.info(f"Sheets: all {len(rows)} rows already present (idempotent)")
            return 0

        logger.info(f"Sheets: writing {len(new_rows)} new rows (skipping {len(rows) - len(new_rows)} duplicates)")

        values = [
            [
                r.email_id, r.subject, r.sender, r.date,
                r.summary, r.category, r.sentiment, r.urgency_label, r.processed_at,
            ]
            for r in new_rows
        ]

        try:
            req = self._service.spreadsheets().values().append(
                spreadsheetId=self._sheet_id,
                range=f"{sheet}!A:I",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": values},
            )
            result = await self._run_sync(req.execute)
            written = result.get("updates", {}).get("updatedRows", len(new_rows))
            logger.info(f"Sheets: wrote {written} rows successfully")
            return written
        except HttpError as exc:
            logger.error(f"Sheets API error: {exc}")
            return 0


def get_sheets_writer() -> SheetsWriter:
    return SheetsWriter()
