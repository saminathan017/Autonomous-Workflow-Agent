from __future__ import annotations

"""
Redis pub/sub event bus for multi-process workflow events.

Any server worker can publish events; any WebSocket subscriber on any
worker will receive them because all workers share the same Redis channel.

Channel name: workflow:events:<run_id>
"""

import asyncio
import json
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

import redis.asyncio as aioredis
from loguru import logger

from autonomous_workflow_agent.app.config import get_settings

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )
    return _redis


async def ping_redis() -> bool:
    try:
        r = await get_redis()
        return bool(await r.ping())
    except Exception as exc:
        logger.warning(f"Redis ping failed: {exc}")
        return False


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("Redis connection closed")


async def publish_event(run_id: str, event: dict) -> None:
    try:
        r = await get_redis()
        await r.publish(f"workflow:events:{run_id}", json.dumps(event))
    except Exception as exc:
        logger.warning(f"Redis publish failed for run {run_id}: {exc}")


@asynccontextmanager
async def subscribe_events(run_id: str) -> AsyncIterator[asyncio.Queue]:
    """
    Async context manager that yields a local asyncio.Queue populated by
    a background pump task reading from Redis pub/sub.

    Usage:
        async with subscribe_events(run_id) as q:
            event = await asyncio.wait_for(q.get(), timeout=30)
    """
    r = await get_redis()
    pubsub = r.pubsub()
    channel = f"workflow:events:{run_id}"
    await pubsub.subscribe(channel)

    local_q: asyncio.Queue[dict] = asyncio.Queue()

    async def _pump() -> None:
        try:
            async for raw in pubsub.listen():
                if raw["type"] == "message":
                    try:
                        local_q.put_nowait(json.loads(raw["data"]))
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning(f"Redis pump error for run {run_id}: {exc}")

    pump_task = asyncio.create_task(_pump())
    try:
        yield local_q
    finally:
        pump_task.cancel()
        with suppress(asyncio.CancelledError):
            await pump_task
        with suppress(Exception):
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
