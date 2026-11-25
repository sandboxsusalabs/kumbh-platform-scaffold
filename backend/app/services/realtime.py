"""In-process pub/sub for the live surfaces: visitor alerts (SSE) and the dashboard
common operating picture (WebSocket).

One process serves many clients; across replicas each pod subscribes to the Redis
channel `kumbh:live` and fans out locally (the hook is marked below).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Set

CHANNEL_ALERTS = "alerts"
CHANNEL_OPS = "ops"


class Broker:
    def __init__(self) -> None:
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {CHANNEL_ALERTS: set(), CHANNEL_OPS: set()}
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.setdefault(channel, set()).add(queue)
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.get(channel, set()).discard(queue)

    async def publish(self, channel: str, message: Dict[str, Any]) -> int:
        """Returns the number of clients the message reached."""
        targets: List[asyncio.Queue] = list(self._subscribers.get(channel, set()))
        for queue in targets:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Slow consumer: drop the message rather than stall the control room.
                pass
        # Cross-replica fan-out hook: PUBLISH kumbh:live <channel>:<json> via Redis here.
        return len(targets)

    @property
    def subscriber_count(self) -> Dict[str, int]:
        return {channel: len(queues) for channel, queues in self._subscribers.items()}


broker = Broker()


def sse_frame(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, separators=(',', ':'))}\n\n"
