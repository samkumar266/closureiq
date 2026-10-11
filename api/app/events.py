"""Small in-process SSE pub/sub for the single-process hackathon MVP."""
from __future__ import annotations

import asyncio
import json
from typing import Any


class EventHub:
    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    async def publish(self, name: str, data: dict[str, Any]) -> None:
        event = {"name": name, "data": data}
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow client: drop its oldest queued event and enqueue the newest one.
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    async def subscribe(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: {event['name']}\ndata: {json.dumps(event['data'], separators=(',', ':'))}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            self._subscribers.discard(queue)


event_hub = EventHub()
