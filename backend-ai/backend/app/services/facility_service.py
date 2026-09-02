"""
facility_service.py — Emergency facility registry and nearest-facility lookup.

For the hackathon prototype, demo hospital data is configured in code.
In production this would be loaded from the database or an external API.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.services.geolocation_service import (
    haversine_distance,
    estimate_eta_minutes,
)

logger = logging.getLogger(__name__)

# ── Demo hospitals (Karachi area — hackathon prototype) ─────────────────

DEMO_FACILITIES: list[dict] = [
    {
        "id": "hospital_001",
        "name": "Jinnah Postgraduate Medical Centre",
        "latitude": 24.8607,
        "longitude": 67.0011,
        "radius_meters": 5000,
        "emergency_capable": True,
    },
    {
        "id": "hospital_002",
        "name": "Aga Khan University Hospital",
        "latitude": 24.8933,
        "longitude": 67.0667,
        "radius_meters": 5000,
        "emergency_capable": True,
    },
    {
        "id": "hospital_003",
        "name": "Civil Hospital Karachi",
        "latitude": 24.8580,
        "longitude": 67.0180,
        "radius_meters": 5000,
        "emergency_capable": True,
    },
    {
        "id": "hospital_004",
        "name": "Liaquat National Hospital",
        "latitude": 24.8710,
        "longitude": 67.0520,
        "radius_meters": 5000,
        "emergency_capable": True,
    },
    {
        "id": "hospital_005",
        "name": "Indus Hospital Korangi",
        "latitude": 24.8350,
        "longitude": 67.1350,
        "radius_meters": 5000,
        "emergency_capable": True,
    },
]


def get_all_facilities() -> list[dict]:
    """Return the full list of configured emergency facilities."""
    return DEMO_FACILITIES


def get_facility_details(facility_id: str) -> Optional[dict]:
    """Return details for a specific facility, or None if not found."""
    for fac in DEMO_FACILITIES:
        if fac["id"] == facility_id:
            return fac
    return None


def find_nearest_emergency_facility(
    latitude: float,
    longitude: float,
) -> Optional[dict]:
    """
    Find the nearest emergency-capable facility to the given coordinates.

    Returns a dict with facility info, distance_km, and estimated_eta_minutes.
    Returns None if no facilities are configured.
    """
    if not DEMO_FACILITIES:
        return None

    nearest = None
    nearest_dist = float("inf")

    for fac in DEMO_FACILITIES:
        if not fac.get("emergency_capable", False):
            continue
        dist = haversine_distance(latitude, longitude,
                                  fac["latitude"], fac["longitude"])
        if dist < nearest_dist:
            nearest_dist = dist
            nearest = fac

    if nearest is None:
        return None

    eta = estimate_eta_minutes(nearest_dist)

    # Check if patient is inside this facility's geofence
    radius = nearest.get("radius_meters", 5000)
    inside = (nearest_dist * 1000) <= radius

    return {
        "facility_id": nearest["id"],
        "facility_name": nearest["name"],
        "latitude": nearest["latitude"],
        "longitude": nearest["longitude"],
        "distance_km": round(nearest_dist, 2),
        "estimated_eta_minutes": eta,
        "inside_geofence": inside,
    }
