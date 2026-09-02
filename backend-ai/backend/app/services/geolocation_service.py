"""
geolocation_service.py — Pure-Python geolocation utilities.

No external mapping libraries required.  Uses the Haversine formula
for great-circle distance and simple coordinate validation.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0
# Average ambulance speed in city (km/h) — used for rough ETA
AVERAGE_CITY_SPEED_KMH = 35.0

# WhatsApp-integration DB path (same DB that stores users/conversations)
_DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..",
                 "..", "whatsapp-integration", "shifa_ai.db")
)


# ── Coordinate validation ───────────────────────────────────────────────

def validate_coordinates(latitude: float, longitude: float) -> bool:
    """Return True if coordinates are within valid ranges."""
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0


# ── Haversine distance ─────────────────────────────────────────────────

def haversine_distance(lat1: float, lng1: float,
                       lat2: float, lng2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth.

    Returns distance in kilometres.
    """
    φ1, λ1 = math.radians(lat1), math.radians(lng1)
    φ2, λ2 = math.radians(lat2), math.radians(lng2)

    dφ = φ2 - φ1
    dλ = λ2 - λ1

    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_KM * c


def estimate_eta_minutes(distance_km: float) -> float:
    """Rough ETA based on distance and average city speed."""
    if distance_km <= 0:
        return 0.0
    return round((distance_km / AVERAGE_CITY_SPEED_KMH) * 60, 1)


# ── Geofence check ──────────────────────────────────────────────────────

def check_geofence(
    lat: float,
    lng: float,
    facilities: list[dict],
) -> dict:
    """
    Check whether the point is inside any facility's geofence radius.

    Returns:
        {
            "inside_geofence": bool,
            "nearest_facility": dict | None,
            "distance_km": float,
        }
    """
    if not facilities:
        return {"inside_geofence": False, "nearest_facility": None, "distance_km": 0.0}

    nearest = None
    nearest_dist = float("inf")
    inside = False

    for fac in facilities:
        dist = haversine_distance(lat, lng, fac["latitude"], fac["longitude"])
        if dist < nearest_dist:
            nearest_dist = dist
            nearest = fac

        radius = fac.get("radius_meters", 5000)
        if dist * 1000 <= radius:
            inside = True

    return {
        "inside_geofence": inside,
        "nearest_facility": nearest,
        "distance_km": round(nearest_dist, 2),
    }


# ── Process location for an emergency ──────────────────────────────────

def process_location(
    emergency_id: str,
    latitude: float,
    longitude: float,
    facilities: list[dict],
    accuracy: Optional[float] = None,
) -> dict:
    """
    Validate, geofence-check, and persist a patient's location for an
    emergency incident.

    Returns a dict with geofence result, nearest facility, and ETA.
    """
    if not validate_coordinates(latitude, longitude):
        raise ValueError("Invalid coordinates")

    geo = check_geofence(latitude, longitude, facilities)
    nearest = geo["nearest_facility"]
    dist_km = geo["distance_km"]
    eta = estimate_eta_minutes(dist_km) if nearest else 0.0

    # Persist to DB
    try:
        if os.path.exists(_DB_PATH):
            conn = sqlite3.connect(_DB_PATH)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                now = datetime.now(tz=timezone.utc).isoformat()
                conn.execute(
                    """UPDATE emergency_incidents
                       SET latitude=?, longitude=?, location_accuracy=?,
                           location_timestamp=?, nearest_facility_id=?,
                           distance_km=?, estimated_eta=?,
                           status='LOCATION_RECEIVED', updated_at=?
                       WHERE id=?""",
                    (latitude, longitude, accuracy, now,
                     nearest["id"] if nearest else None,
                     dist_km, eta, now, emergency_id),
                )
                # Log event
                conn.execute(
                    """INSERT INTO emergency_events
                       (emergency_id, event_type, event_data)
                       VALUES (?, 'LOCATION_RECEIVED', ?)""",
                    (emergency_id, json.dumps({
                        "latitude": latitude,
                        "longitude": longitude,
                        "distance_km": dist_km,
                        "nearest_facility": nearest["id"] if nearest else None,
                        "inside_geofence": geo["inside_geofence"],
                    })),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as exc:
        logger.error("Failed to persist location for %s: %s", emergency_id, exc)

    return {
        "inside_geofence": geo["inside_geofence"],
        "nearest_facility": nearest,
        "distance_km": dist_km,
        "estimated_eta_minutes": eta,
    }
