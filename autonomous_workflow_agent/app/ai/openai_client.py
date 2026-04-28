from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIError
from loguru import logger

from autonomous_workflow_agent.app.config import get_settings


@dataclass
class CompletionResult:
    success: bool
    content: str = ""
    tool_result: dict[str, Any] | None = None
    usage: dict[str, int] = field(default_factory=dict)
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class OpenAIClient:
    """
    Async OpenAI client with:
    - Function calling for guaranteed structured JSON outputs
    - asyncio.Semaphore to cap concurrent requests (rate-limit protection)
    - Exponential-backoff retry on 429 RateLimitError
    - Per-run call budget to prevent runaway API costs
    - Token tracking for cost monitoring
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file.")
        self._client = AsyncOpenAI(
            api_key=self._settings.openai_api_key,
            timeout=float(self._settings.openai_timeout_seconds),
        )
        # Hard cap on concurrent outbound requests — prevents 429 bursts
        self._semaphore = asyncio.Semaphore(self._settings.openai_concurrency_limit)
        self._call_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def reset_run_counters(self) -> None:
        self._call_count = 0

    @property
    def calls_remaining(self) -> int:
        return self._settings.openai_max_calls_per_run - self._call_count

    @property
    def stats(self) -> dict[str, int]:
        return {
            "calls": self._call_count,
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
        }

    async def complete(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> CompletionResult:
        if self._call_count >= self._settings.openai_max_calls_per_run:
            return CompletionResult(
                success=False,
                error=f"Run budget exhausted ({self._settings.openai_max_calls_per_run} calls/run)",
            )

        target_model = model or self._settings.openai_model
        max_tok = max_tokens or self._settings.openai_max_tokens
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict[str, Any] = {
            "model": target_model,
            "max_tokens": max_tok,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        async with self._semaphore:
            for attempt in range(3):
                try:
                    response = await self._client.chat.completions.create(**kwargs)
                    self._call_count += 1

                    inp = response.usage.prompt_tokens
                    out = response.usage.completion_tokens
                    self._total_input_tokens += inp
                    self._total_output_tokens += out

                    msg = response.choices[0].message

                    if msg.tool_calls:
                        tc = msg.tool_calls[0]
                        try:
                            parsed = json.loads(tc.function.arguments)
                        except json.JSONDecodeError as exc:
                            return CompletionResult(success=False, error=f"JSON parse error: {exc}")
                        return CompletionResult(
                            success=True,
                            tool_result={"name": tc.function.name, "input": parsed},
                            usage={"input_tokens": inp, "output_tokens": out},
                            input_tokens=inp,
                            output_tokens=out,
                        )

                    return CompletionResult(
                        success=True,
                        content=msg.content or "",
                        usage={"input_tokens": inp, "output_tokens": out},
                        input_tokens=inp,
                        output_tokens=out,
                    )

                except RateLimitError:
                    wait = 5 * (2 ** attempt)
                    logger.warning(
                        f"OpenAI rate limited — retrying in {wait}s (attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(wait)

                except APITimeoutError:
                    if attempt == 2:
                        return CompletionResult(
                            success=False, error="Request timed out after 3 attempts"
                        )
                    await asyncio.sleep(2)

                except APIError as exc:
                    logger.error(f"OpenAI API error: {exc}")
                    return CompletionResult(success=False, error=str(exc))

        return CompletionResult(success=False, error="Max retries exceeded")


_instance: OpenAIClient | None = None


def get_openai_client() -> OpenAIClient:
    global _instance
    if _instance is None:
        _instance = OpenAIClient()
    return _instance
