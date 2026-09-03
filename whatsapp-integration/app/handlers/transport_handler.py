"""
transport_handler.py — Handles user's emergency transport selection.

After location is received, the user is offered three transport options:
  1. Ambulance  — triggers existing mock dispatch flow
  2. InDrive    — generates InDrive deep-link to nearest facility
  3. Uber       — generates Uber deep-link to nearest facility

User responds with "1", "2", or "3" to select their transport.
"""

from __future__ import annotations

import logging
import re
import urllib.parse

import requests

from app.config import config
from app.services.meta_sender import send_whatsapp_message
from app.handlers.emergency_messages import (
    detect_user_language,
    transport_booked_confirmation,
)
from app.handlers.emergency_handler import (
    _get_active_emergency,
    handle_dispatch_notification,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Transport selection patterns ────────────────────────────────────────

_TRANSPORT_PATTERN = re.compile(
    r"^\s*([1-3])\s*$",
    re.IGNORECASE,
)

# Map numeric choice to transport type key
_CHOICE_MAP = {
    "1": "ambulance",
    "2": "indrive",
    "3": "uber",
}


def is_transport_selection(text: str) -> bool:
    """Return True if the message is a transport option selection (1, 2, or 3)."""
    return bool(_TRANSPORT_PATTERN.match(text.strip()))


def handle_transport_selection(from_number: str, text: str) -> None:
    """
    Process the user's transport choice.

    Args:
        from_number: Sender's phone number
        text: The raw message text (expected "1", "2", or "3")
    """
    match = _TRANSPORT_PATTERN.match(text.strip())
    if not match:
        return

    choice = match.group(1)
    transport_type = _CHOICE_MAP[choice]

    logger.info(
        "Transport selected | from=%s | choice=%s | type=%s",
        from_number, choice, transport_type,
    )

    # Get active emergency for facility info
    active = _get_active_emergency(from_number)
    facility = ""
    lat = 0.0
    lng = 0.0

    if active:
        emergency_id = active.get("id", "")
        facility = active.get("nearest_facility", "") or ""
        lat = active.get("latitude") or 0.0
        lng = active.get("longitude") or 0.0

        if transport_type == "ambulance":
            # Trigger existing mock dispatch
            handle_dispatch_notification(from_number, emergency_id)
            # Also send confirmation
            lang = detect_user_language(from_number)
            msg = transport_booked_confirmation(
                lang=lang,
                transport_type=transport_type,
                facility=facility,
                lat=lat,
                lng=lng,
            )
            send_whatsapp_message(from_number, msg)
            return

        # For InDrive / Uber — generate deep link with hospital as destination
        _send_ride_link(from_number, transport_type, lat, lng, facility)

    else:
        # No active emergency — still send a generic ride link
        _send_ride_link(from_number, transport_type, 0.0, 0.0, "")

    # Send confirmation
    lang = detect_user_language(from_number)
    msg = transport_booked_confirmation(
        lang=lang,
        transport_type=transport_type,
        facility=facility,
        lat=lat,
        lng=lng,
    )
    send_whatsapp_message(from_number, msg)


def _send_ride_link(
    from_number: str,
    transport_type: str,
    lat: float,
    lng: float,
    facility: str,
) -> None:
    """Generate and send a deep-link for InDrive or Uber."""
    dest_label = facility or "Emergency Hospital"

    if transport_type == "indrive":
        # InDrive deep-link: open app with pickup/dropoff
        # https://indrive.com/app/?dropoff_lat=...&dropoff_lng=...&dropoff_name=...
        if lat and lng:
            params = urllib.parse.urlencode({
                "dropoff_lat": lat,
                "dropoff_lng": lng,
                "dropoff_name": dest_label,
            })
            link = f"https://indrive.com/app/?{params}"
        else:
            link = "https://indrive.com/app/"
        link_msg = f"🚕 *InDrive — Book Your Ride*\n{link}"

    elif transport_type == "uber":
        # Uber deep-link: https://m.uber.com/ul/?action=setPickup&dropoff[latitude]=...
        if lat and lng:
            params = urllib.parse.urlencode({
                "action": "setPickup",
                "dropoff[latitude]": lat,
                "dropoff[longitude]": lng,
                "dropoff[nickname]": dest_label,
            })
            link = f"https://m.uber.com/ul/?{params}"
        else:
            link = "https://m.uber.com/ul/"
        link_msg = f"🚙 *Uber — Book Your Ride*\n{link}"
    else:
        return

    send_whatsapp_message(from_number, link_msg)
    logger.info("Ride link sent | from=%s | type=%s", from_number, transport_type)
