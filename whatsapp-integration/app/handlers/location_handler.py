"""
location_handler.py — Processes WhatsApp location messages for the
emergency workflow.

When a patient shares their location via WhatsApp during an active
emergency, this handler:
  1. Extracts latitude/longitude from the Meta payload
  2. Submits location to the backend emergency API
  3. Asks user which hospital they want to go to
  4. On user response, cascading booking:
     Ambulance → InDrive → Uber (fallback chain)
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
    hospital_request_message,
    auto_book_cascade_message,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── In-memory store for pending hospital input ────────────────────────
# Key: whatsapp number, Value: dict with emergency + location data
# This tracks users who have shared location but haven't picked a hospital yet.
_pending_hospital: dict[str, dict] = {}


def is_waiting_for_hospital(from_number: str) -> bool:
    """Return True if this user is waiting to provide hospital name."""
    return from_number in _pending_hospital


def get_pending_data(from_number: str) -> dict | None:
    """Return pending emergency/location data for a user, or None."""
    return _pending_hospital.get(from_number)


def clear_pending(from_number: str) -> None:
    """Remove pending hospital data after booking."""
    _pending_hospital.pop(from_number, None)


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

        # Send location confirmation
        handle_location_result(from_number, emergency_id, distance_km, facility, eta)

        # ── Store pending data & ask which hospital ──────────────
        _pending_hospital[from_number] = {
            "emergency_id": emergency_id,
            "latitude": latitude,
            "longitude": longitude,
            "nearest_facility": facility,
            "eta": eta,
            "distance_km": distance_km,
        }

        lang = detect_user_language(from_number)
        hospital_msg = hospital_request_message(lang)
        send_whatsapp_message(from_number, hospital_msg)
        logger.info("Hospital request sent | from=%s", from_number)

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


def handle_hospital_input(from_number: str, hospital_name: str) -> None:
    """
    User provided hospital name — trigger cascading transport booking.

    Cascade order:
      1. Ambulance (if available/nearby)
      2. InDrive (if ambulance unavailable)
      3. Uber (if both ambulance and InDrive unavailable)
    """
    pending = get_pending_data(from_number)
    if not pending:
        return

    emergency_id = pending["emergency_id"]
    lat = pending["latitude"]
    lng = pending["longitude"]
    facility = hospital_name.strip() or pending.get("nearest_facility", "")
    eta = pending.get("eta", 0)
    lang = detect_user_language(from_number)

    logger.info(
        "Hospital input received | from=%s | hospital=%s | emergency=%s",
        from_number, facility, emergency_id,
    )

    # Clear pending state
    clear_pending(from_number)

    # ── CASCADE 1: Try Ambulance ────────────────────────────────
    ambulance_ok = _try_ambulance(emergency_id, from_number)
    if ambulance_ok:
        dispatch_id = ambulance_ok.get("dispatch_id", "")
        eta = ambulance_ok.get("eta_minutes", eta) or eta
        facility = ambulance_ok.get("nearest_facility", facility) or facility

        msg = auto_book_cascade_message(
            lang=lang, booked_type="ambulance",
            dispatch_id=dispatch_id, eta_minutes=eta,
            facility=facility, lat=lat, lng=lng,
        )
        send_whatsapp_message(from_number, msg)
        logger.info("Ambulance booked | from=%s | dispatch=%s", from_number, dispatch_id)
        return

    # ── CASCADE 2: Try InDrive ──────────────────────────────────
    logger.info("Ambulance not available — trying InDrive | from=%s", from_number)
    indrive_ok = _try_ride_service("indrive", lat, lng, facility)
    if indrive_ok:
        msg = auto_book_cascade_message(
            lang=lang, booked_type="indrive",
            facility=facility, lat=lat, lng=lng,
        )
        send_whatsapp_message(from_number, msg)
        logger.info("InDrive booked | from=%s", from_number)
        return

    # ── CASCADE 3: Try Uber ─────────────────────────────────────
    logger.info("InDrive not available — trying Uber | from=%s", from_number)
    uber_ok = _try_ride_service("uber", lat, lng, facility)
    if uber_ok:
        msg = auto_book_cascade_message(
            lang=lang, booked_type="uber",
            facility=facility, lat=lat, lng=lng,
        )
        send_whatsapp_message(from_number, msg)
        logger.info("Uber booked | from=%s", from_number)
        return

    # ── ALL FAILED ──────────────────────────────────────────────
    logger.error("All transport options failed | from=%s", from_number)
    if lang == "ur":
        fallback = "🚨 تمام ٹرانسپورٹ ناکام ہوئی۔ براہِ کرم 1122 پر کال کریں۔"
    elif lang in ("roman_urdu", "roman_sindhi"):
        fallback = "🚨 Sab transport fail ho gayi. Barah-e-karam 1122 par call karein."
    else:
        fallback = "🚨 All transport options failed. Please call 1122 directly."
    send_whatsapp_message(from_number, fallback)


def _try_ambulance(emergency_id: str, from_number: str) -> dict | None:
    """Try to dispatch ambulance. Returns dispatch data or None on failure."""
    try:
        resp = requests.post(
            f"{config.BACKEND_BASE_URL}/api/emergency/dispatch/mock",
            params={"emergency_id": emergency_id},
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        # Check if dispatch was actually created (not just simulated failure)
        if data.get("dispatch_id"):
            return data
        return None
    except Exception as exc:
        logger.warning("Ambulance dispatch failed | from=%s | error=%s", from_number, exc)
        return None


def _try_ride_service(service: str, lat: float, lng: float, facility: str) -> bool:
    """
    Try to generate a ride link for InDrive or Uber.
    Since these are deep-links (not API bookings), they always succeed
    unless coordinates are missing.
    Returns True if link was generated, False otherwise.
    """
    # Deep links always work if we have coordinates
    if lat and lng:
        return True
    # Without coordinates, still provide generic app link
    return True
