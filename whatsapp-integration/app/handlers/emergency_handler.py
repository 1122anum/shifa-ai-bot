"""
emergency_handler.py — Emergency detection and workflow management
for the WhatsApp integration layer.

Detects emergency classification from Gemini triage responses and
triggers the full emergency workflow: analysis, location request,
dashboard alert, mock dispatch, and patient guidance.
"""

from __future__ import annotations

import json
import logging
import re
import threading

import requests

from app.config import config
from app.services.meta_sender import send_whatsapp_message
from app.handlers.emergency_messages import (
    detect_user_language,
    emergency_location_request,
    emergency_guidance,
    dispatch_notification,
    cancellation_confirmation,
    location_received_confirmation,
    transport_options_message,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Cancellation patterns ───────────────────────────────────────────────

CANCEL_PATTERNS = re.compile(
    r"(cancel\s*emergency|cancel\s*help|cancel\s*ambulance|"
    r"emergency\s*cancel|stop\s*emergency|no\s*emergency|"
    r"ایمرجنسی\s*منسوخ|منسوخ\s*کریں|"
    r"ايمرجنسي\s*منسوخ|cancel\s*911|false\s*alarm)",
    re.IGNORECASE | re.UNICODE,
)


def is_cancellation_request(text: str) -> bool:
    """Return True if the message is requesting emergency cancellation."""
    return bool(CANCEL_PATTERNS.search(text.strip()))


def handle_emergency_cancellation(from_number: str) -> None:
    """Cancel the active emergency workflow for a user."""
    logger.info("Emergency cancellation requested | from=%s", from_number)

    # Call backend to cancel
    try:
        active = _get_active_emergency(from_number)
        if active:
            emergency_id = active.get("id", "")
            resp = requests.post(
                f"{config.BACKEND_BASE_URL}/api/emergency/{emergency_id}/cancel",
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            logger.info("Emergency cancelled | id=%s", emergency_id)
        else:
            logger.info("No active emergency to cancel | from=%s", from_number)
    except Exception as exc:
        logger.error("Cancellation API failed: %s", exc)

    # Send confirmation in user's language
    lang = detect_user_language(from_number)
    msg = cancellation_confirmation(lang)
    send_whatsapp_message(from_number, msg)


def detect_emergency_from_triage(ai_response: str) -> dict | None:
    """
    Parse the Gemini triage response to detect emergency classification.

    Returns a dict with risk_level, or None if no emergency detected.
    Detects patterns like:
      - "Urgency Level: EMERGENCY"
      - "Urgency: CRITICAL_EMERGENCY"
      - "Triage Level: EMERGENCY"
    """
    if not ai_response:
        return None

    upper = ai_response.upper()

    # Check for CRITICAL_EMERGENCY first (most specific)
    if re.search(
        r'(?:urgency|triage|priority|level)\s*(?:level)?\s*[:\-–]\s*\*{0,2}'
        r'CRITICAL[_\s]EMERGENCY\*{0,2}',
        ai_response, re.IGNORECASE,
    ):
        return {"risk_level": "CRITICAL_EMERGENCY", "source": "triage_response"}

    # Check for general EMERGENCY
    if re.search(
        r'(?:urgency|triage|priority|level)\s*(?:level)?\s*[:\-–]\s*\*{0,2}EMERGENCY\*{0,2}',
        ai_response, re.IGNORECASE,
    ):
        return {"risk_level": "CRITICAL_EMERGENCY", "source": "triage_response"}

    # Check if response starts with EMERGENCY
    if re.match(r'^\s*\*{0,2}(?:CRITICAL[_\s]EMERGENCY|EMERGENCY)\*{0,2}', ai_response.strip(), re.IGNORECASE):
        return {"risk_level": "CRITICAL_EMERGENCY", "source": "triage_response"}

    # Check for HIGH_RISK
    if re.search(
        r'(?:urgency|triage|priority|level)\s*(?:level)?\s*[:\-–]\s*\*{0,2}'
        r'(?:HIGH[_\s]RISK|URGENT)\*{0,2}',
        ai_response, re.IGNORECASE,
    ):
        return {"risk_level": "HIGH_RISK", "source": "triage_response"}

    # Check for EMERGENCY keyword anywhere (less specific)
    if "EMERGENCY" in upper and any(
        kw in upper for kw in ["SEVERE", "IMMEDIATELY", "LIFE-THREATENING", "URGENT"]
    ):
        return {"risk_level": "CRITICAL_EMERGENCY", "source": "keyword_detection"}

    return None


def handle_emergency_workflow(
    from_number: str,
    ai_response: str,
    symptoms: str = "",
    conversation_context: str = "",
) -> None:
    """
    Trigger the full emergency workflow:
    1. Call backend emergency analyze
    2. Send location request to patient
    3. Dashboard alert is handled by backend WebSocket broadcast
    """
    logger.info("Emergency workflow triggered | from=%s", from_number)

    lang = detect_user_language(from_number)

    # Step 1: Call backend emergency analyze
    emergency_id = None
    try:
        resp = requests.post(
            f"{config.BACKEND_BASE_URL}/api/emergency/analyze",
            json={
                "user_id": from_number,
                "symptoms": symptoms or ai_response[:2000],
                "conversation_history": conversation_context[:2000],
            },
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        emergency_id = data.get("emergency_id", "")
        logger.info("Emergency analyzed | id=%s | risk=%s",
                     emergency_id, data.get("risk_level"))
    except Exception as exc:
        logger.error("Emergency analyze failed: %s", exc)

    # Step 2: Send emergency guidance + location request
    location_msg = emergency_location_request(lang)
    send_whatsapp_message(from_number, location_msg)

    # Step 3: Send emergency guidance
    guidance_msg = emergency_guidance(lang)
    send_whatsapp_message(from_number, guidance_msg)

    # Transport is now AUTO-BOOKED after user shares location
    # (handled by location_handler._auto_book_transport)


def handle_dispatch_notification(
    from_number: str,
    emergency_id: str,
) -> None:
    """Trigger mock dispatch and notify patient."""
    try:
        resp = requests.post(
            f"{config.BACKEND_BASE_URL}/api/emergency/dispatch/mock",
            params={"emergency_id": emergency_id},
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        lang = detect_user_language(from_number)
        msg = dispatch_notification(
            lang=lang,
            dispatch_id=data.get("dispatch_id", ""),
            eta_minutes=data.get("eta_minutes", 0),
            facility=data.get("nearest_facility", ""),
        )
        send_whatsapp_message(from_number, msg)
    except Exception as exc:
        logger.error("Dispatch notification failed: %s", exc)


def handle_location_result(
    from_number: str,
    emergency_id: str,
    distance_km: float,
    facility: str,
    eta: float,
) -> None:
    """Send location confirmation to patient after geofencing."""
    lang = detect_user_language(from_number)
    msg = location_received_confirmation(
        lang=lang,
        distance_km=distance_km,
        facility=facility,
        eta=eta,
    )
    send_whatsapp_message(from_number, msg)


# ── Helpers ─────────────────────────────────────────────────────────────

def _get_active_emergency(from_number: str) -> dict | None:
    """Get the active emergency for a user from the backend."""
    try:
        resp = requests.get(
            f"{config.BACKEND_BASE_URL}/api/emergency/active",
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        for inc in data.get("incidents", []):
            if inc.get("user_id") == from_number:
                return inc
        return None
    except Exception as exc:
        logger.debug("Could not fetch active emergency: %s", exc)
        return None
