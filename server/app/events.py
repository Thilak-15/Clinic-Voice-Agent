"""Tiny in-process pub/sub so the dashboard hears about changes.

The voice bot publishes events (availability checked, appointment booked or
cancelled); the /api/events endpoint streams them to every open dashboard as
Server-Sent Events.
"""

import asyncio
import json
from typing import Any

_subscribers: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def publish(event_type: str, **data: Any) -> None:
    message = json.dumps({"type": event_type, **data}, default=str)
    for q in list(_subscribers):
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            pass  # slow client; drop rather than block the bot
