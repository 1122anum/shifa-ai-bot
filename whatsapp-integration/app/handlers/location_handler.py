"""
location_handler.py — Processes WhatsApp location messages for the
emergency workflow.

When a patient shares their location via WhatsApp during an active
emergency, this handler:
  1. Extracts latitude/longitude from the Meta payload
  2. Submits location to the backend emergency API
  3. Sends confirmation to the patient
"""

from __future__ import annotations

import logging

import requests

from app.config import config
from app.services.meta_sender import send_whatsapp_message
from app.handlers.emergency_handler import (
    _get_active_emergency,
    handle_location_result,
)
from app.handlers.emergency_messages import (
    detect_user_language,
    location_received_confirmation,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def handle_location_message(from_number: str, location_data: dict) -> None:
    """
    Process a WhatsApp location message.

    Args:
        from_number: Sender's phone number
        location_data: Meta location payload with keys:
            latitude, longitude, name (optional), address (optional)
    """
    latitude = location_data.get("latitude")
    longitude = location_data.get("longitude")

    if latitude is None or longitude is None:
        logger.warning("Location message missing coordinates | from=%s", from_number)
        send_whatsapp_message(
            from_number,
            "Could not read your location. Please try sharing your location again.",
        )
        return

    logger.info(
        "Location received | from=%s | lat=%.4f | lng=%.4f",
        from_number, latitude, longitude,
    )

    # Find active emergency for this user
    active = _get_active_emergency(from_number)

    if not active:
        # No active emergency — still acknowledge the location
        lang = detect_user_language(from_number)
        send_whatsapp_message(
            from_number,
            "📍 Location received. Thank you.\n"
            "There is no active emergency workflow at this time.\n"
            "If you are in an emergency, please describe your symptoms.",
        )
        return

    emergency_id = active.get("id", "")
    accuracy = location_data.get("accuracy")

    # Submit location to backend
    try:
        resp = requests.post(
            f"{config.BACKEND_BASE_URL}/api/emergency/{emergency_id}/location",
            json={
                "emergency_id": emergency_id,
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": accuracy,
            },
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        distance_km = data.get("distance_km", 0)
        facility = data.get("nearest_facility", "") or ""
        eta = data.get("estimated_eta_minutes", 0)

        logger.info(
            "Location processed | emergency=%s | distance=%.1f km | facility=%s",
            emergency_id, distance_km, facility,
        )

        # Send confirmation to patient
        handle_location_result(from_number, emergency_id, distance_km, facility, eta)

    except requests.exceptions.ConnectionError:
        logger.error("Backend unavailable for location submission")
        send_whatsapp_message(
            from_number,
            "📍 Location received but the system is temporarily unavailable.\n"
            "Please contact your local emergency service directly.",
        )
    except Exception as exc:
        logger.error("Location submission failed: %s", exc)
        send_whatsapp_message(
            from_number,
            "📍 Location received. An error occurred while processing.\n"
            "Please contact your local emergency service if your situation is urgent.",
        )
