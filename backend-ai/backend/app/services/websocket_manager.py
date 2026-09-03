"""
websocket_manager.py — FastAPI WebSocket connection manager for the
emergency dashboard.

Supports:
  - Multiple concurrent dashboard connections
  - Token-based authentication via query param (?token=...)
  - Broadcasting emergency events to all connected clients
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections for the emergency dashboard."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connected | total=%d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket disconnected | total=%d", len(self.active_connections))

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send an event to all connected dashboard clients."""
        payload = json.dumps(event, default=str)
        disconnected: list[WebSocket] = []
        for ws in self.active_connections:
            try:
                await ws.send_text(payload)
            except Exception:
                disconnected.append(ws)

        # Clean up dead connections
        for ws in disconnected:
            self.disconnect(ws)

        logger.debug("WebSocket broadcast | event=%s | clients=%d",
                     event.get("event", "unknown"), len(self.active_connections))


def verify_dashboard_token(token: str) -> bool:
    """Verify the dashboard access token using constant-time comparison."""
    import hmac
    expected = settings.DASHBOARD_SECRET_TOKEN
    if not expected or not token:
        return False
    return hmac.compare_digest(token, expected)


# Singleton manager instance
ws_manager = ConnectionManager()
