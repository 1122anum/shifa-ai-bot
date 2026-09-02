"""
emergency.py — FastAPI router for the Emergency Geofencing Engine.

Endpoints for emergency analysis, location submission, incident
management, facility lookup, and mock dispatch.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.emergency import (
    EmergencyAnalyzeRequest,
    EmergencyAnalyzeResponse,
    EmergencyDetailResponse,
    LocationSubmitRequest,
    FacilityResponse,
    DispatchResponse,
)
from app.services import emergency_service
from app.services import geolocation_service
from app.services import facility_service
from app.services import dispatch_service
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

# WhatsApp-integration DB path
_DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..",
                 "..", "whatsapp-integration", "shifa_ai.db")
)

router = APIRouter(tags=["emergency"])


# ── Emergency Analysis ──────────────────────────────────────────────────

@router.post("/analyze", response_model=EmergencyAnalyzeResponse)
async def analyze_emergency(req: EmergencyAnalyzeRequest):
    """
    Analyze symptoms for emergency classification.

    Uses Gemini to classify urgency as ROUTINE, HIGH_RISK, or
    CRITICAL_EMERGENCY. Returns structured result with risk level,
    category, confidence, and red flags.
    """
    vital_data = None
    if req.vital_data:
        vital_data = req.vital_data.model_dump()

    result = emergency_service.analyze_emergency(
        symptoms=req.symptoms,
        conversation_history=req.conversation_history,
        vital_data=vital_data,
        user_id=req.user_id,
    )

    response = EmergencyAnalyzeResponse(
        emergency_id=result.get("emergency_id", ""),
        risk_level=result.get("risk_level", "ROUTINE"),
        category=result.get("category"),
        confidence=result.get("confidence", 0.0),
        red_flags=result.get("red_flags", []),
        requires_emergency_workflow=result.get("requires_emergency_workflow", False),
        message=result.get("message", ""),
    )

    # Broadcast to dashboard if critical
    if response.requires_emergency_workflow:
        await ws_manager.broadcast({
            "event": "EMERGENCY_DETECTED",
            "emergency_id": response.emergency_id,
            "risk_level": response.risk_level,
            "category": response.category,
            "confidence": response.confidence,
            "red_flags": response.red_flags,
            "user_id": req.user_id,
        })

    return response


# ── Active Emergencies ──────────────────────────────────────────────────

@router.get("/active")
async def list_active_emergencies():
    """Return all active (non-resolved, non-cancelled) emergency incidents."""
    incidents = _query_incidents(active_only=True)
    return {"status": "success", "incidents": incidents}


# ── Single Emergency Detail ─────────────────────────────────────────────

@router.get("/{emergency_id}")
async def get_emergency(emergency_id: str):
    """Get full details of a specific emergency incident."""
    incident = _query_incident_by_id(emergency_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Emergency not found")
    return EmergencyDetailResponse(**incident)


# ── Acknowledge ─────────────────────────────────────────────────────────

@router.post("/{emergency_id}/acknowledge")
async def acknowledge_emergency(emergency_id: str):
    """Dashboard acknowledges an emergency alert."""
    incident = _query_incident_by_id(emergency_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Emergency not found")

    # Update dashboard_alert_status
    _update_field(emergency_id, "dashboard_alert_status", "ACKNOWLEDGED")
    emergency_service.transition_state(emergency_id, "DASHBOARD_ALERTED")

    await ws_manager.broadcast({
        "event": "DASHBOARD_ALERT",
        "emergency_id": emergency_id,
        "action": "acknowledged",
    })

    return {"status": "success", "message": "Emergency acknowledged"}


# ── Resolve ─────────────────────────────────────────────────────────────

@router.post("/{emergency_id}/resolve")
async def resolve_emergency(emergency_id: str):
    """Mark an emergency as resolved."""
    incident = _query_incident_by_id(emergency_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Emergency not found")

    success = emergency_service.transition_state(emergency_id, "RESOLVED")
    if not success:
        # Force resolve even if state transition is invalid
        _update_field(emergency_id, "status", "RESOLVED")
        _update_field(emergency_id, "resolved_at",
                      _now_iso())

    await ws_manager.broadcast({
        "event": "EMERGENCY_RESOLVED",
        "emergency_id": emergency_id,
    })

    return {"status": "success", "message": "Emergency resolved"}


# ── Cancel ──────────────────────────────────────────────────────────────

@router.post("/{emergency_id}/cancel")
async def cancel_emergency(emergency_id: str):
    """Cancel an emergency (e.g. accidental trigger)."""
    incident = _query_incident_by_id(emergency_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Emergency not found")

    _update_field(emergency_id, "status", "CANCELLED")
    _update_field(emergency_id, "resolved_at", _now_iso())

    _log_event(emergency_id, "EMERGENCY_CANCELLED", {})

    await ws_manager.broadcast({
        "event": "EMERGENCY_CANCELLED",
        "emergency_id": emergency_id,
    })

    return {
        "status": "success",
        "message": (
            "Emergency cancelled. Note: If symptoms remain potentially "
            "life-threatening, please seek emergency medical care immediately."
        ),
    }


# ── Location Submission ─────────────────────────────────────────────────

@router.post("/{emergency_id}/location")
async def submit_location(emergency_id: str, req: LocationSubmitRequest):
    """Submit the patient's location for an emergency incident."""
    incident = _query_incident_by_id(emergency_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Emergency not found")

    facilities = facility_service.get_all_facilities()

    try:
        result = geolocation_service.process_location(
            emergency_id=emergency_id,
            latitude=req.latitude,
            longitude=req.longitude,
            facilities=facilities,
            accuracy=req.accuracy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Broadcast location update
    await ws_manager.broadcast({
        "event": "LOCATION_RECEIVED",
        "emergency_id": emergency_id,
        "latitude": req.latitude,
        "longitude": req.longitude,
        "distance_km": result["distance_km"],
        "nearest_facility": result["nearest_facility"]["name"] if result["nearest_facility"] else None,
    })

    return {
        "status": "success",
        "inside_geofence": result["inside_geofence"],
        "distance_km": result["distance_km"],
        "estimated_eta_minutes": result["estimated_eta_minutes"],
        "nearest_facility": result["nearest_facility"]["name"] if result["nearest_facility"] else None,
    }


# ── Nearest Facility ────────────────────────────────────────────────────

@router.get("/facilities/nearest", response_model=FacilityResponse)
async def nearest_facility(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
):
    """Find the nearest emergency facility from coordinates."""
    result = facility_service.find_nearest_emergency_facility(latitude, longitude)
    if not result:
        raise HTTPException(status_code=404, detail="No facilities configured")
    return FacilityResponse(**result)


# ── Mock Dispatch ───────────────────────────────────────────────────────

@router.post("/dispatch/mock")
async def create_mock_dispatch(emergency_id: str):
    """Create a mock ambulance dispatch for an emergency."""
    incident = _query_incident_by_id(emergency_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Emergency not found")

    try:
        result = dispatch_service.create_dispatch_request(
            emergency_id=emergency_id,
            latitude=incident.get("latitude"),
            longitude=incident.get("longitude"),
            category=incident.get("category", "OTHER_CRITICAL"),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Broadcast dispatch status
    await ws_manager.broadcast({
        "event": "DISPATCH_STATUS",
        "emergency_id": emergency_id,
        "dispatch_id": result["dispatch_id"],
        "status": result["status"],
        "eta_minutes": result["eta_minutes"],
    })

    return DispatchResponse(
        dispatch_id=result["dispatch_id"],
        status=result["status"],
        vehicle_type=result["vehicle_type"],
        eta_minutes=result["eta_minutes"],
        message=result["message"],
    )


# ── Emergency Events Log ───────────────────────────────────────────────

@router.get("/{emergency_id}/events")
async def get_emergency_events(emergency_id: str):
    """Get the audit event log for an emergency incident."""
    events = _query_events(emergency_id)
    return {"status": "success", "emergency_id": emergency_id, "events": events}


# ── Database helpers ────────────────────────────────────────────────────

def _db_connect():
    if not os.path.exists(_DB_PATH):
        return None
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _query_incidents(active_only: bool = False) -> list[dict]:
    conn = _db_connect()
    if not conn:
        return []
    try:
        if active_only:
            rows = conn.execute(
                """SELECT * FROM emergency_incidents
                   WHERE status NOT IN ('RESOLVED', 'CANCELLED')
                   ORDER BY
                     CASE risk_level
                       WHEN 'CRITICAL_EMERGENCY' THEN 1
                       WHEN 'HIGH_RISK' THEN 2
                       ELSE 3
                     END,
                     created_at DESC"""
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM emergency_incidents ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def _query_incident_by_id(emergency_id: str) -> Optional[dict]:
    conn = _db_connect()
    if not conn:
        return None
    try:
        row = conn.execute(
            "SELECT * FROM emergency_incidents WHERE id = ?",
            (emergency_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def _query_events(emergency_id: str) -> list[dict]:
    conn = _db_connect()
    if not conn:
        return []
    try:
        rows = conn.execute(
            """SELECT id, emergency_id, event_type, event_data, created_at
               FROM emergency_events
               WHERE emergency_id = ?
               ORDER BY created_at ASC""",
            (emergency_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("event_data"):
                try:
                    d["event_data"] = json.loads(d["event_data"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result
    finally:
        conn.close()


def _update_field(emergency_id: str, field: str, value) -> None:
    conn = _db_connect()
    if not conn:
        return
    try:
        conn.execute(
            f"UPDATE emergency_incidents SET {field}=?, updated_at=? WHERE id=?",
            (value, _now_iso(), emergency_id),
        )
        conn.commit()
    finally:
        conn.close()


def _log_event(emergency_id: str, event_type: str, data: dict) -> None:
    conn = _db_connect()
    if not conn:
        return
    try:
        conn.execute(
            """INSERT INTO emergency_events
               (emergency_id, event_type, event_data)
               VALUES (?, ?, ?)""",
            (emergency_id, event_type, json.dumps(data)),
        )
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a regular dict, parsing red_flags JSON."""
    d = dict(row)
    if d.get("red_flags"):
        try:
            d["red_flags"] = json.loads(d["red_flags"])
        except (json.JSONDecodeError, TypeError):
            d["red_flags"] = []
    else:
        d["red_flags"] = []
    return d
