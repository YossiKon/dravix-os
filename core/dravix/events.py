"""A tiny async pub/sub event bus.

Modes, integrations, and the API publish/subscribe to named events here. Subscribers get an
``asyncio.Queue`` of ``Event`` objects.
"""
from __future__ import annotations

import asyncio
import collections
import time
from dataclasses import dataclass, field
from typing import Any

from .logging import get_logger

log = get_logger("events")


@dataclass(slots=True)
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        # A short memory of what just happened, so the dashboard's live activity feed
        # paints instantly on load instead of starting empty.
        self.recent: collections.deque[Event] = collections.deque(maxlen=100)

    def subscribe(self, maxsize: int = 100) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(q)

    async def publish(self, type: str, **data: Any) -> None:
        event = Event(type=type, data=data)
        self.recent.append(event)
        log.debug("event %s %s", event.type, event.data)
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the oldest, keep the newest — a slow subscriber must not block others.
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass
