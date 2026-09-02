"""
test_emergency.py — Tests for the Emergency Geofencing Engine.

Covers: emergency classification, geofencing, dispatch, state machine,
location validation, facility lookup, and API endpoints.
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock

# Set env vars before importing app
os.environ.setdefault("EMERGENCY_DISPATCH_MODE", "MOCK")
os.environ.setdefault("DASHBOARD_SECRET_TOKEN", "shifa_dashboard_2024")
os.environ.setdefault("GEMINI_API_KEY", "test_key_dummy")
os.environ.setdefault("EMERGENCY_COOLDOWN_MINUTES", "10")


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


# ── Tests: Geolocation Service ─────────────────────────────────────

class TestGeolocation:

    def test_validate_valid_coordinates(self):
        from app.services.geolocation_service import validate_coordinates
        assert validate_coordinates(24.8607, 67.0011) is True

    def test_validate_invalid_latitude(self):
        from app.services.geolocation_service import validate_coordinates
        assert validate_coordinates(91.0, 67.0) is False

    def test_validate_invalid_longitude(self):
        from app.services.geolocation_service import validate_coordinates
        assert validate_coordinates(24.0, 181.0) is False

    def test_validate_negative_coordinates(self):
        from app.services.geolocation_service import validate_coordinates
        assert validate_coordinates(-33.87, 151.21) is True

    def test_validate_non_numeric(self):
        from app.services.geolocation_service import validate_coordinates
        assert validate_coordinates("abc", "def") is False

    def test_haversine_distance_same_point(self):
        from app.services.geolocation_service import haversine_distance
        assert haversine_distance(24.86, 67.00, 24.86, 67.00) == 0.0

    def test_haversine_distance_known(self):
        from app.services.geolocation_service import haversine_distance
        # Karachi to Islamabad ~ approximately 1100 km
        dist = haversine_distance(24.8607, 67.0011, 33.6844, 73.0479)
        assert 1000 < dist < 1300

    def test_estimate_eta(self):
        from app.services.geolocation_service import estimate_eta_minutes
        eta = estimate_eta_minutes(7.0)
        assert eta > 0
        assert isinstance(eta, float)

    def test_check_geofence_inside(self):
        from app.services.geolocation_service import check_geofence
        facilities = [
            {"id": "h1", "name": "Hospital A", "latitude": 24.86, "longitude": 67.00,
             "radius_meters": 5000},
        ]
        result = check_geofence(24.861, 67.001, facilities)
        assert result["inside_geofence"] is True
        assert result["nearest_facility"]["id"] == "h1"

    def test_check_geofence_outside(self):
        from app.services.geolocation_service import check_geofence
        facilities = [
            {"id": "h1", "name": "Hospital A", "latitude": 24.86, "longitude": 67.00,
             "radius_meters": 500},
        ]
        result = check_geofence(25.0, 67.5, facilities)
        assert result["inside_geofence"] is False

    def test_check_geofence_empty_facilities(self):
        from app.services.geolocation_service import check_geofence
        result = check_geofence(24.86, 67.00, [])
        assert result["inside_geofence"] is False
        assert result["nearest_facility"] is None


# ── Tests: Facility Service ────────────────────────────────────────

class TestFacility:

    def test_get_all_facilities(self):
        from app.services.facility_service import get_all_facilities
        facilities = get_all_facilities()
        assert len(facilities) >= 1
        assert "id" in facilities[0]
        assert "name" in facilities[0]

    def test_get_facility_details_found(self):
        from app.services.facility_service import get_facility_details
        fac = get_facility_details("hospital_001")
        assert fac is not None
        assert fac["id"] == "hospital_001"

    def test_get_facility_details_not_found(self):
        from app.services.facility_service import get_facility_details
        assert get_facility_details("nonexistent") is None

    def test_find_nearest_facility(self):
        from app.services.facility_service import find_nearest_emergency_facility
        result = find_nearest_emergency_facility(24.86, 67.00)
        assert result is not None
        assert "facility_id" in result
        assert "distance_km" in result
        assert result["distance_km"] >= 0

    def test_nearest_facility_has_eta(self):
        from app.services.facility_service import find_nearest_emergency_facility
        result = find_nearest_emergency_facility(24.87, 67.05)
        assert result is not None
        assert result["estimated_eta_minutes"] >= 0


# ── Tests: Dispatch Service ────────────────────────────────────────

class TestDispatch:

    @patch("app.services.dispatch_service._DB_PATH", "/nonexistent/path.db")
    def test_mock_dispatch_success(self):
        from app.services.dispatch_service import create_dispatch_request
        result = create_dispatch_request(
            emergency_id="emg_test_001",
            latitude=24.86,
            longitude=67.00,
            category="CHEST_PAIN",
        )
        assert result["dispatch_id"].startswith("MOCK-")
        assert result["status"] == "DISPATCH_SIMULATED"
        assert result["vehicle_type"] == "AMBULANCE"
        assert "SIMULATED" in result["message"]

    @patch("app.services.dispatch_service._DB_PATH", "/nonexistent/path.db")
    def test_mock_dispatch_without_location(self):
        from app.services.dispatch_service import create_dispatch_request
        result = create_dispatch_request(
            emergency_id="emg_test_002",
            latitude=None,
            longitude=None,
            category="BREATHING_EMERGENCY",
        )
        assert result["dispatch_id"].startswith("MOCK-")
        assert result["eta_minutes"] == 10.0  # default mock ETA

    @patch("app.services.dispatch_service._dispatch_mode", return_value="PRODUCTION")
    def test_production_dispatch_raises(self, mock_mode):
        from app.services.dispatch_service import create_dispatch_request
        with pytest.raises(RuntimeError, match="Production dispatch is not configured"):
            create_dispatch_request("emg_003", 24.86, 67.00, "CHEST_PAIN")


# ── Tests: State Machine ───────────────────────────────────────────

class TestStateMachine:

    def test_valid_transition_normal_to_assessing(self):
        from app.models.emergency import is_valid_transition
        assert is_valid_transition("NORMAL", "ASSESSING") is True

    def test_valid_transition_assessing_to_emergency(self):
        from app.models.emergency import is_valid_transition
        assert is_valid_transition("ASSESSING", "EMERGENCY_DETECTED") is True

    def test_invalid_transition_resolved_to_normal(self):
        from app.models.emergency import is_valid_transition
        assert is_valid_transition("RESOLVED", "NORMAL") is False

    def test_invalid_transition_cancelled_to_dispatch(self):
        from app.models.emergency import is_valid_transition
        assert is_valid_transition("CANCELLED", "DISPATCH_PENDING") is False

    def test_valid_transition_dispatch_to_confirmed(self):
        from app.models.emergency import is_valid_transition
        assert is_valid_transition("DISPATCH_PENDING", "DISPATCH_CONFIRMED") is True

    def test_valid_transition_guidance_to_resolved(self):
        from app.models.emergency import is_valid_transition
        assert is_valid_transition("PATIENT_GUIDANCE_SENT", "RESOLVED") is True


# ── Tests: Emergency API Endpoints ─────────────────────────────────

class TestEmergencyAPI:

    @patch("app.services.emergency_service.analyze_emergency")
    def test_analyze_emergency_endpoint(self, mock_analyze, client):
        mock_analyze.return_value = {
            "emergency_id": "emg_test_001",
            "risk_level": "CRITICAL_EMERGENCY",
            "category": "CHEST_PAIN",
            "confidence": 0.95,
            "red_flags": ["severe chest pain"],
            "requires_emergency_workflow": True,
            "message": "",
        }
        r = client.post("/api/emergency/analyze", json={
            "user_id": "923001234567",
            "symptoms": "Severe chest pain and difficulty breathing",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["risk_level"] == "CRITICAL_EMERGENCY"
        assert data["requires_emergency_workflow"] is True

    def test_analyze_empty_symptoms_rejected(self, client):
        r = client.post("/api/emergency/analyze", json={
            "user_id": "923001234567",
            "symptoms": "",
        })
        assert r.status_code == 422

    @patch("app.api.emergency._query_incidents")
    def test_active_emergencies_empty(self, mock_query, client):
        mock_query.return_value = []
        r = client.get("/api/emergency/active")
        assert r.status_code == 200
        assert r.json()["incidents"] == []

    @patch("app.api.emergency._query_incident_by_id")
    def test_get_emergency_not_found(self, mock_query, client):
        mock_query.return_value = None
        r = client.get("/api/emergency/nonexistent_id")
        assert r.status_code == 404

    def test_nearest_facility_endpoint(self, client):
        r = client.get("/api/emergency/facilities/nearest?latitude=24.86&longitude=67.00")
        assert r.status_code == 200
        data = r.json()
        assert "facility_id" in data
        assert "distance_km" in data

    def test_nearest_facility_invalid_coords(self, client):
        r = client.get("/api/emergency/facilities/nearest?latitude=200&longitude=67.00")
        assert r.status_code == 422

    def test_dashboard_page_served(self, client):
        r = client.get("/dashboard/emergencies")
        assert r.status_code == 200
        assert b"Emergency Dashboard" in r.content

    def test_root_lists_emergency_endpoints(self, client):
        r = client.get("/")
        assert r.status_code == 200
        endpoints = r.json()["endpoints"]
        assert "emergency_analyze" in endpoints
        assert "emergency_active" in endpoints
        assert "dashboard" in endpoints


# ── Tests: Emergency Keyword Fallback ──────────────────────────────

class TestKeywordFallback:

    def test_chest_pain_detected(self):
        from app.services.emergency_service import _keyword_fallback
        result = _keyword_fallback("I have severe chest pain")
        assert result["risk_level"] == "CRITICAL_EMERGENCY"

    def test_unconscious_detected(self):
        from app.services.emergency_service import _keyword_fallback
        result = _keyword_fallback("The patient is unconscious")
        assert result["risk_level"] == "CRITICAL_EMERGENCY"

    def test_high_fever_detected(self):
        from app.services.emergency_service import _keyword_fallback
        result = _keyword_fallback("I have a high fever")
        assert result["risk_level"] == "HIGH_RISK"

    def test_routine_symptoms(self):
        from app.services.emergency_service import _keyword_fallback
        result = _keyword_fallback("I have a mild headache")
        assert result["risk_level"] == "ROUTINE"


# ── Tests: WebSocket Manager ──────────────────────────────────────

class TestWebSocketManager:

    def test_verify_valid_token(self):
        from app.services.websocket_manager import verify_dashboard_token
        assert verify_dashboard_token("shifa_dashboard_2024") is True

    def test_verify_invalid_token(self):
        from app.services.websocket_manager import verify_dashboard_token
        assert verify_dashboard_token("wrong_token") is False
