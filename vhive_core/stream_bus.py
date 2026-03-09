"""
Star-Office-UI: Event bus for real-time streaming to WebSocket clients.
LangGraph state changes, CrewAI agent thoughts, and Docker terminal outputs
are emitted here and broadcast to all connected /ws clients.
"""

import asyncio
import json
import queue
from typing import Any

from fastapi import WebSocket


class StreamBroadcaster:
    """Broadcasts events to all connected WebSocket clients."""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self._event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)

    async def emit(self, event_type: str, payload: Any) -> None:
        """Emit an event to all connected clients."""
        msg = {"type": event_type, "payload": payload}
        text = json.dumps(msg, default=str)
        dead = []
        async with self._lock:
            for conn in self._connections:
                try:
                    await conn.send_text(text)
                except Exception:
                    dead.append(conn)
        for conn in dead:
            await self.disconnect(conn)

    def emit_sync(self, event_type: str, payload: Any) -> None:
        """Synchronous emit - enqueues for async broadcast. Use from sync code (e.g. workflow thread)."""
        self._event_queue.put((event_type, payload))

    async def drain_queue(self) -> None:
        """Drain pending events from the queue and broadcast. Call from async context."""
        while not self._event_queue.empty():
            try:
                event_type, payload = self._event_queue.get_nowait()
                await self.emit(event_type, payload)
            except queue.Empty:
                break


# Global broadcaster instance
broadcaster = StreamBroadcaster()
