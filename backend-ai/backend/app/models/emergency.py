"""
emergency.py — Pydantic models for the Emergency Geofencing Engine.

Defines request/response schemas, enums for risk levels, emergency
categories, and the explicit emergency state machine.
"""

from __future__ import annotations

import enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ───────────────────────────────────────────────────────────────

class RiskLevel(str, enum.Enum):
    ROUTINE = "ROUTINE"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL_EMERGENCY = "CRITICAL_EMERGENCY"


class EmergencyCategory(str, enum.Enum):
    CHEST_PAIN = "CHEST_PAIN"
    BREATHING_EMERGENCY = "BREATHING_EMERGENCY"
    STROKE_WARNING = "STROKE_WARNING"
    LOSS_OF_CONSCIOUSNESS = "LOSS_OF_CONSCIOUSNESS"
    SEVERE_BLEEDING = "SEVERE_BLEEDING"
    SEVERE_ALLERGIC_REACTION = "SEVERE_ALLERGIC_REACTION"
    TRAUMA = "TRAUMA"
    OTHER_CRITICAL = "OTHER_CRITICAL"


class EmergencyState(str, enum.Enum):
    NORMAL = "NORMAL"
    ASSESSING = "ASSESSING"
    HIGH_RISK = "HIGH_RISK"
    EMERGENCY_DETECTED = "EMERGENCY_DETECTED"
    LOCATION_REQUESTED = "LOCATION_REQUESTED"
    LOCATION_RECEIVED = "LOCATION_RECEIVED"
    DASHBOARD_ALERTED = "DASHBOARD_ALERTED"
    DISPATCH_PENDING = "DISPATCH_PENDING"
    DISPATCH_CONFIRMED = "DISPATCH_CONFIRMED"
    PATIENT_GUIDANCE_SENT = "PATIENT_GUIDANCE_SENT"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


# ── State machine ───────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[str, set[str]] = {
    "NORMAL": {"ASSESSING"},
    "ASSESSING": {"EMERGENCY_DETECTED", "HIGH_RISK", "NORMAL"},
    "HIGH_RISK": {"EMERGENCY_DETECTED", "NORMAL"},
    "EMERGENCY_DETECTED": {"LOCATION_REQUESTED"},
    "LOCATION_REQUESTED": {"LOCATION_RECEIVED", "PATIENT_GUIDANCE_SENT"},
    "LOCATION_RECEIVED": {"DASHBOARD_ALERTED"},
    "DASHBOARD_ALERTED": {"DISPATCH_PENDING"},
    "DISPATCH_PENDING": {"DISPATCH_CONFIRMED", "PATIENT_GUIDANCE_SENT"},
    "DISPATCH_CONFIRMED": {"PATIENT_GUIDANCE_SENT"},
    "PATIENT_GUIDANCE_SENT": {"RESOLVED"},
    "RESOLVED": set(),
    "CANCELLED": set(),
}


def is_valid_transition(current: str, target: str) -> bool:
    """Return True if the state transition is allowed."""
    allowed = VALID_TRANSITIONS.get(current, set())
    return target in allowed


# ── Request models ──────────────────────────────────────────────────────

class VitalContextData(BaseModel):
    heart_rate: Optional[int] = None
    respiration_rate: Optional[int] = None
    heart_rate_confidence: Optional[float] = None
    respiration_confidence: Optional[float] = None
    signal_quality: Optional[str] = None


class EmergencyAnalyzeRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=256)
    symptoms: str = Field(..., min_length=1, max_length=4000)
    conversation_history: str = Field(default="")
    vital_data: Optional[VitalContextData] = None


class LocationSubmitRequest(BaseModel):
    emergency_id: str = Field(..., min_length=1)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = None


# ── Response models ─────────────────────────────────────────────────────

class EmergencyAnalyzeResponse(BaseModel):
    status: str = "success"
    emergency_id: str
    risk_level: str
    category: Optional[str] = None
    confidence: float = 0.0
    red_flags: list[str] = Field(default_factory=list)
    requires_emergency_workflow: bool = False
    message: str = ""


class EmergencyDetailResponse(BaseModel):
    emergency_id: str
    user_id: str
    risk_level: str
    category: Optional[str] = None
    confidence: float = 0.0
    red_flags: list[str] = Field(default_factory=list)
    status: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    nearest_facility_id: Optional[str] = None
    distance_km: Optional[float] = None
    estimated_eta: Optional[float] = None
    dispatch_id: Optional[str] = None
    dispatch_status: Optional[str] = None
    dashboard_alert_status: Optional[str] = None
    vital_context: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    resolved_at: Optional[str] = None


class FacilityResponse(BaseModel):
    facility_id: str
    facility_name: str
    latitude: float
    longitude: float
    distance_km: float
    estimated_eta_minutes: float
    inside_geofence: bool = False


class DispatchResponse(BaseModel):
    dispatch_id: str
    status: str
    vehicle_type: str = "AMBULANCE"
    eta_minutes: float = 0.0
    message: str = ""


class EmergencyEventResponse(BaseModel):
    id: int
    emergency_id: str
    event_type: str
    event_data: Optional[str] = None
    created_at: Optional[str] = None
