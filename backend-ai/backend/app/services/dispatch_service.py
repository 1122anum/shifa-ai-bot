"""
dispatch_service.py — Emergency dispatch engine.

Supports two modes controlled by EMERGENCY_DISPATCH_MODE env var:
  - MOCK: Simulates ambulance dispatch for demo/hackathon
  - PRODUCTION: Requires an authorised dispatch provider (not implemented)

IMPORTANT: The mock dispatch is NOT a real ambulance dispatch.
Never tell a patient that a real ambulance is coming unless an
authorised production provider has confirmed it.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.services.geolocation_service import estimate_eta_minutes, haversine_distance
from app.services.facility_service import find_nearest_emergency_facility

logger = logging.getLogger(__name__)

# WhatsApp-integration DB path
_DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..",
                 "..", "whatsapp-integration", "shifa_ai.db")
)


def _dispatch_mode() -> str:
    return settings.EMERGENCY_DISPATCH_MODE


def create_dispatch_request(
    emergency_id: str,
    latitude: Optional[float],
    longitude: Optional[float],
    category: str,
) -> dict:
    """
    Create a dispatch request for an emergency incident.

    In MOCK mode, generates a simulated dispatch response.
    In PRODUCTION mode, raises an error if no authorised provider is configured.

    Returns:
        dict with dispatch_id, status, vehicle_type, eta_minutes, message
    """
    mode = _dispatch_mode()

    if mode == "PRODUCTION":
        raise RuntimeError(
            "Production dispatch is not configured. "
            "An authorised dispatch provider must be set up before "
            "real emergency vehicles can be dispatched."
        )

    # ── MOCK DISPATCH ────────────────────────────────────────
    dispatch_id = f"MOCK-{secrets.token_hex(4).upper()}"

    # Estimate ETA if location available
    eta = 10.0  # default mock ETA
    nearest = None
    if latitude is not None and longitude is not None:
        nearest = find_nearest_emergency_facility(latitude, longitude)
        if nearest:
            eta = nearest["estimated_eta_minutes"]

    result = {
        "dispatch_id": dispatch_id,
        "status": "DISPATCH_SIMULATED",
        "vehicle_type": "AMBULANCE",
        "eta_minutes": eta,
        "nearest_facility": nearest["facility_name"] if nearest else "Unknown",
        "message": (
            "DEMO / SIMULATED DISPATCH — This is NOT a real ambulance. "
            "In a real emergency, contact your local emergency services immediately."
        ),
    }

    # Persist to DB
    _persist_dispatch(emergency_id, dispatch_id, result)

    logger.info(
        "Mock dispatch created | emergency=%s | dispatch=%s | eta=%.1f min",
        emergency_id, dispatch_id, eta,
    )
    return result


def _persist_dispatch(emergency_id: str, dispatch_id: str, result: dict) -> None:
    """Save dispatch result and log event to the database."""
    try:
        if not os.path.exists(_DB_PATH):
            return
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            now = datetime.now(tz=timezone.utc).isoformat()
            conn.execute(
                """UPDATE emergency_incidents
                   SET dispatch_id=?, dispatch_status='DISPATCH_SIMULATED',
                       status='DISPATCH_CONFIRMED', updated_at=?
                   WHERE id=?""",
                (dispatch_id, now, emergency_id),
            )
            conn.execute(
                """INSERT INTO emergency_events
                   (emergency_id, event_type, event_data)
                   VALUES (?, 'DISPATCH_SIMULATED', ?)""",
                (emergency_id, json.dumps({
                    "dispatch_id": dispatch_id,
                    "eta_minutes": result["eta_minutes"],
                    "vehicle_type": result["vehicle_type"],
                    "mode": "MOCK",
                })),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Failed to persist dispatch: %s", exc)


def get_active_dispatches() -> list[dict]:
    """Return all active (non-resolved) dispatch IDs."""
    try:
        if not os.path.exists(_DB_PATH):
            return []
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT id, dispatch_id, dispatch_status
               FROM emergency_incidents
               WHERE dispatch_id IS NOT NULL
                 AND status NOT IN ('RESOLVED', 'CANCELLED')""",
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []
