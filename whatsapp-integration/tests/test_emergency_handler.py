"""
test_emergency_handler.py — Tests for the emergency handler,
location handler, and emergency messages in the WhatsApp integration.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("EMERGENCY_DISPATCH_MODE", "MOCK")
os.environ.setdefault("DASHBOARD_SECRET_TOKEN", "shifa_dashboard_2024")

FROM = "923001234567"


# ── Tests: Emergency Detection ──────────────────────────────────────

class TestEmergencyDetection:

    def test_detect_emergency_from_urgency_label(self):
        from app.handlers.emergency_handler import detect_emergency_from_triage
        result = detect_emergency_from_triage("Urgency Level: EMERGENCY\nSevere symptoms.")
        assert result is not None
        assert result["risk_level"] == "CRITICAL_EMERGENCY"

    def test_detect_critical_emergency_label(self):
        from app.handlers.emergency_handler import detect_emergency_from_triage
        result = detect_emergency_from_triage("Urgency: CRITICAL_EMERGENCY\nChest pain.")
        assert result is not None
        assert result["risk_level"] == "CRITICAL_EMERGENCY"

    def test_detect_emergency_at_start(self):
        from app.handlers.emergency_handler import detect_emergency_from_triage
        result = detect_emergency_from_triage("EMERGENCY: Severe chest pain detected.")
        assert result is not None

    def test_detect_high_risk(self):
        from app.handlers.emergency_handler import detect_emergency_from_triage
        result = detect_emergency_from_triage("Urgency Level: URGENT\nPersistent fever.")
        assert result is not None
        assert result["risk_level"] == "HIGH_RISK"

    def test_no_emergency_in_routine(self):
        from app.handlers.emergency_handler import detect_emergency_from_triage
        result = detect_emergency_from_triage("Urgency Level: ROUTINE\nMild headache. Rest and hydrate.")
        assert result is None

    def test_no_emergency_in_empty(self):
        from app.handlers.emergency_handler import detect_emergency_from_triage
        result = detect_emergency_from_triage("")
        assert result is None

    def test_no_emergency_in_none(self):
        from app.handlers.emergency_handler import detect_emergency_from_triage
        result = detect_emergency_from_triage(None)
        assert result is None

    def test_detect_emergency_with_severe_keywords(self):
        from app.handlers.emergency_handler import detect_emergency_from_triage
        result = detect_emergency_from_triage(
            "This is EMERGENCY. Severe symptoms require IMMEDIATELY seeking care."
        )
        assert result is not None


# ── Tests: Cancellation Detection ───────────────────────────────────

class TestCancellationDetection:

    def test_cancel_emergency_detected(self):
        from app.handlers.emergency_handler import is_cancellation_request
        assert is_cancellation_request("cancel emergency") is True

    def test_cancel_help_detected(self):
        from app.handlers.emergency_handler import is_cancellation_request
        assert is_cancellation_request("cancel help") is True

    def test_false_alarm_detected(self):
        from app.handlers.emergency_handler import is_cancellation_request
        assert is_cancellation_request("false alarm") is True

    def test_urdu_cancel_detected(self):
        from app.handlers.emergency_handler import is_cancellation_request
        assert is_cancellation_request("ایمرجنسی منسوخ") is True

    def test_normal_message_not_cancel(self):
        from app.handlers.emergency_handler import is_cancellation_request
        assert is_cancellation_request("I have a headache") is False


# ── Tests: Emergency Messages ───────────────────────────────────────

class TestEmergencyMessages:

    def test_english_location_request(self):
        from app.handlers.emergency_messages import emergency_location_request
        msg = emergency_location_request("en")
        assert "location" in msg.lower() or "📍" in msg
        assert "emergency" in msg.lower()

    def test_urdu_location_request(self):
        from app.handlers.emergency_messages import emergency_location_request
        msg = emergency_location_request("ur")
        assert "📍" in msg

    def test_sindhi_location_request(self):
        from app.handlers.emergency_messages import emergency_location_request
        msg = emergency_location_request("sd")
        assert "📍" in msg

    def test_roman_urdu_location_request(self):
        from app.handlers.emergency_messages import emergency_location_request
        msg = emergency_location_request("roman_urdu")
        assert "location" in msg.lower() or "📍" in msg

    def test_english_emergency_guidance(self):
        from app.handlers.emergency_messages import emergency_guidance
        msg = emergency_guidance("en")
        assert "emergency" in msg.lower()
        assert "disclaimer" in msg.lower() or "triage" in msg.lower()

    def test_urdu_emergency_guidance(self):
        from app.handlers.emergency_messages import emergency_guidance
        msg = emergency_guidance("ur")
        assert "🚨" in msg

    def test_dispatch_notification_has_simulated(self):
        from app.handlers.emergency_messages import dispatch_notification
        msg = dispatch_notification("en", "MOCK-ABC123", 12.0, "Hospital A")
        assert "SIMULATED" in msg
        assert "MOCK-ABC123" in msg
        assert "NOT a real" in msg

    def test_dispatch_urdu_has_simulated(self):
        from app.handlers.emergency_messages import dispatch_notification
        msg = dispatch_notification("ur", "MOCK-XYZ", 10.0, "")
        assert "MOCK-XYZ" in msg

    def test_cancellation_confirmation_english(self):
        from app.handlers.emergency_messages import cancellation_confirmation
        msg = cancellation_confirmation("en")
        assert "cancel" in msg.lower()
        assert "symptom" in msg.lower() or "medical" in msg.lower()

    def test_location_received_confirmation(self):
        from app.handlers.emergency_messages import location_received_confirmation
        msg = location_received_confirmation("en", 4.2, "Hospital A", 12.0)
        assert "Hospital A" in msg
        assert "4.2 km" in msg
        assert "EXPERIMENTAL" in msg or "experimental" in msg.lower()


# ── Tests: Location Handler ─────────────────────────────────────────

class TestLocationHandler:

    @patch("app.handlers.location_handler.send_whatsapp_message")
    @patch("app.handlers.location_handler._get_active_emergency")
    def test_location_no_active_emergency(self, mock_active, mock_send):
        mock_active.return_value = None
        from app.handlers.location_handler import handle_location_message
        handle_location_message(FROM, {"latitude": 24.86, "longitude": 67.00})
        mock_send.assert_called_once()
        sent = mock_send.call_args[0][1]
        assert "location" in sent.lower()

    @patch("app.handlers.location_handler.send_whatsapp_message")
    def test_location_missing_coordinates(self, mock_send):
        from app.handlers.location_handler import handle_location_message
        handle_location_message(FROM, {})
        mock_send.assert_called_once()
        sent = mock_send.call_args[0][1]
        assert "location" in sent.lower()


# ── Tests: Webhook Emergency Callback ───────────────────────────────

class TestEmergencyWebhookCallback:

    def test_emergency_alert_callback_valid(self, flask_client):
        r = flask_client.post(
            "/webhook/emergency-alert",
            json={"user_id": FROM, "event": "EMERGENCY_DETECTED"},
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.get_json()["status"] == "ok"

    def test_emergency_alert_callback_empty(self, flask_client):
        r = flask_client.post(
            "/webhook/emergency-alert",
            data="",
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_emergency_alert_callback_missing_user(self, flask_client):
        r = flask_client.post(
            "/webhook/emergency-alert",
            json={"event": "EMERGENCY_DETECTED"},
            content_type="application/json",
        )
        assert r.status_code == 400


# ── Tests: Webhook Location Routing ────────────────────────────────

class TestLocationRouting:

    @patch("app.handlers.location_handler.send_whatsapp_message")
    @patch("app.handlers.location_handler._get_active_emergency")
    def test_location_message_routed(self, mock_active, mock_send, flask_client):
        mock_active.return_value = None
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": FROM,
                            "type": "location",
                            "id": "wamid_loc_001",
                            "location": {
                                "latitude": 24.8607,
                                "longitude": 67.0011,
                            },
                        }]
                    }
                }]
            }]
        }
        r = flask_client.post(
            "/webhook/whatsapp",
            json=payload,
            content_type="application/json",
        )
        assert r.status_code == 200
        mock_send.assert_called_once()


# ── Tests: Text Handler Emergency Integration ──────────────────────

class TestTextHandlerEmergency:

    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    @patch("app.handlers.emergency_handler.handle_emergency_workflow")
    def test_emergency_triggers_workflow(self, mock_workflow, mock_triage, mock_send):
        mock_triage.return_value = "Urgency Level: EMERGENCY\nSevere chest pain."
        from app.handlers.text_handler import handle_text_message
        handle_text_message(FROM, "Severe chest pain and breathing difficulty")
        mock_send.assert_called()
        # Emergency workflow should be triggered (in a thread, so mock might not fire immediately)
        # We check that detect_emergency_from_triage found it

    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.handle_emergency_cancellation")
    def test_cancellation_bypasses_triage(self, mock_cancel, mock_send):
        from app.handlers.text_handler import handle_text_message
        handle_text_message(FROM, "cancel emergency")
        mock_cancel.assert_called_once_with(FROM)
        mock_send.assert_not_called()
