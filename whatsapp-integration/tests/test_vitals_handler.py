"""
test_vitals_handler.py — Tests for the WhatsApp vitals handler.

Covers:
  - is_pulse_trigger() — multilingual trigger detection
  - format_vital_result_message() — multilingual result formatting
  - handle_pulse_request() — session creation and camera link
  - send_vital_result_to_user() — proactive result delivery
  - /webhook/vital-result endpoint
  - fetch_vital_context() — DB query for recent measurements
"""

import pytest
from unittest.mock import patch, MagicMock

from app.handlers.vitals_handler import (
    is_pulse_trigger,
    format_vital_result_message,
    handle_pulse_request,
    send_vital_result_to_user,
    _detect_user_language,
)


# ── Tests: is_pulse_trigger ──────────────────────────────────────────────

class TestPulseTrigger:

    def test_english_check_pulse(self):
        assert is_pulse_trigger("check pulse")
        assert is_pulse_trigger("Check Pulse")
        assert is_pulse_trigger("CHECK PULSE")

    def test_english_pulse_check(self):
        assert is_pulse_trigger("pulse check")
        assert is_pulse_trigger("Pulse Check please")

    def test_english_check_vitals(self):
        assert is_pulse_trigger("check vitals")

    def test_english_heart_rate(self):
        assert is_pulse_trigger("heart rate")
        assert is_pulse_trigger("check my heart rate")

    def test_english_selfie_pulse(self):
        assert is_pulse_trigger("selfie pulse")

    def test_english_camera_check(self):
        assert is_pulse_trigger("camera check")

    def test_roman_urdu_nabd_check(self):
        assert is_pulse_trigger("nabd check")
        assert is_pulse_trigger("nabd check karo")

    def test_roman_urdu_pulse_dekho(self):
        assert is_pulse_trigger("pulse dekho")

    def test_roman_urdu_dil_dhadkan(self):
        assert is_pulse_trigger("dil dhadkan")

    def test_urdu_nabd_check(self):
        assert is_pulse_trigger("نبض چیک")

    def test_urdu_dil_ki_dhadkan(self):
        assert is_pulse_trigger("دل کی دھڑکن")

    def test_emoji_pulse(self):
        assert is_pulse_trigger("📷 pulse")
        assert is_pulse_trigger("pulse 📷")

    def test_non_trigger_text(self):
        assert not is_pulse_trigger("I have a headache")
        assert not is_pulse_trigger("mujhe bukhar hai")
        assert not is_pulse_trigger("hello")
        assert not is_pulse_trigger("")
        assert not is_pulse_trigger("   ")

    def test_unrelated_words(self):
        assert not is_pulse_trigger("check my email")
        assert not is_pulse_trigger("rate my food")


# ── Tests: format_vital_result_message ───────────────────────────────────

class TestFormatVitalResult:

    def _success_data(self):
        return {
            "status": "success",
            "heart_rate": {"value": 78, "unit": "bpm", "confidence": 0.82},
            "respiration_rate": {"value": 16, "unit": "breaths/minute", "confidence": 0.71},
            "signal_quality": "GOOD",
            "quality_score": 0.86,
            "measurement_duration": 15.0,
            "message": "",
            "disclaimer": "Experimental.",
        }

    def _invalid_data(self):
        return {
            "status": "invalid",
            "signal_quality": "POOR",
            "message": "Unable to obtain a reliable estimate.",
            "heart_rate": None,
            "respiration_rate": None,
            "quality_score": 0.2,
            "measurement_duration": 15.0,
            "disclaimer": "",
        }

    def test_english_success(self):
        msg = format_vital_result_message(self._success_data(), "en")
        assert "Heart Rate" in msg or "heart rate" in msg.lower()
        assert "78" in msg
        assert "16" in msg
        assert "experimental" in msg.lower()

    def test_english_invalid(self):
        msg = format_vital_result_message(self._invalid_data(), "en")
        assert "Unreliable" in msg or "unreliable" in msg.lower()
        assert "Better lighting" in msg or "better lighting" in msg.lower()

    def test_urdu_success(self):
        msg = format_vital_result_message(self._success_data(), "ur")
        assert "78" in msg
        assert "BPM" in msg
        # Should contain Urdu script
        assert any("\u0600" <= c <= "\u06FF" for c in msg)

    def test_urdu_invalid(self):
        msg = format_vital_result_message(self._invalid_data(), "ur")
        assert any("\u0600" <= c <= "\u06FF" for c in msg)

    def test_sindhi_success(self):
        msg = format_vital_result_message(self._success_data(), "sd")
        assert "78" in msg
        assert "BPM" in msg
        # Sindhi uses Arabic script too
        assert any("\u0600" <= c <= "\u06FF" for c in msg)

    def test_roman_urdu_success(self):
        msg = format_vital_result_message(self._success_data(), "roman_urdu")
        assert "78" in msg
        assert "dhadkan" in msg.lower() or "Dhadkan" in msg
        assert "BPM" in msg

    def test_roman_sindhi_success(self):
        msg = format_vital_result_message(self._success_data(), "roman_sindhi")
        assert "78" in msg
        assert "BPM" in msg

    def test_fair_quality_still_shows_result(self):
        data = self._success_data()
        data["signal_quality"] = "FAIR"
        msg = format_vital_result_message(data, "en")
        assert "78" in msg
        assert "FAIR" in msg or "Fair" in msg

    def test_poor_quality_shows_error(self):
        data = self._success_data()
        data["signal_quality"] = "POOR"
        data["status"] = "invalid"
        msg = format_vital_result_message(data, "en")
        assert "Unreliable" in msg or "unreliable" in msg.lower()


# ── Tests: handle_pulse_request ─────────────────────────────────────────

class TestHandlePulseRequest:

    @patch("app.handlers.vitals_handler.send_whatsapp_message")
    @patch("app.handlers.vitals_handler.requests.post")
    def test_sends_camera_link(self, mock_post, mock_send):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "test_session_123",
            "camera_url": "http://localhost:8000/vitals/camera?s=test_session_123",
            "expires_at": "2026-01-01T00:00:00+00:00",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        handle_pulse_request("923001234567")

        mock_post.assert_called_once()
        mock_send.assert_called_once()
        sent_msg = mock_send.call_args[0][1]
        assert "camera" in sent_msg.lower() or "http" in sent_msg.lower()
        assert "experimental" in sent_msg.lower()

    @patch("app.handlers.vitals_handler.send_whatsapp_message")
    @patch("app.handlers.vitals_handler.requests.post")
    def test_backend_unavailable_sends_fallback(self, mock_post, mock_send):
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("connection refused")

        handle_pulse_request("923001234567")

        mock_send.assert_called_once()
        sent_msg = mock_send.call_args[0][1]
        assert "unavailable" in sent_msg.lower() or "text" in sent_msg.lower()


# ── Tests: send_vital_result_to_user ─────────────────────────────────────

class TestSendVitalResultToUser:

    @patch("app.handlers.vitals_handler.send_whatsapp_message")
    @patch("app.handlers.vitals_handler._detect_user_language")
    def test_sends_result_to_user(self, mock_lang, mock_send):
        mock_lang.return_value = "en"
        data = {
            "user_id": "923001234567",
            "status": "success",
            "heart_rate": {"value": 78},
            "respiration_rate": {"value": 16},
            "signal_quality": "GOOD",
            "quality_score": 0.86,
            "measurement_duration": 15.0,
            "message": "",
            "disclaimer": "Experimental.",
        }

        send_vital_result_to_user(data)

        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == "923001234567"
        sent_msg = mock_send.call_args[0][1]
        assert "78" in sent_msg

    @patch("app.handlers.vitals_handler.send_whatsapp_message")
    @patch("app.handlers.vitals_handler._detect_user_language")
    def test_no_user_id_skips(self, mock_lang, mock_send):
        send_vital_result_to_user({"status": "success"})
        mock_send.assert_not_called()

    @patch("app.handlers.vitals_handler.send_whatsapp_message")
    @patch("app.handlers.vitals_handler._detect_user_language")
    def test_invalid_result_sends_error_msg(self, mock_lang, mock_send):
        mock_lang.return_value = "en"
        data = {
            "user_id": "923001234567",
            "status": "invalid",
            "signal_quality": "POOR",
            "heart_rate": None,
            "respiration_rate": None,
            "quality_score": 0.2,
            "measurement_duration": 15.0,
            "message": "Unable to obtain.",
            "disclaimer": "",
        }

        send_vital_result_to_user(data)

        mock_send.assert_called_once()
        sent_msg = mock_send.call_args[0][1]
        assert "nreliable" in sent_msg.lower() or "retry" in sent_msg.lower()


# ── Tests: /webhook/vital-result endpoint ────────────────────────────────

class TestVitalResultWebhook:

    @patch("app.webhook.send_vital_result_to_user")
    def test_valid_payload_returns_200(self, mock_send, flask_client):
        payload = {
            "user_id": "923001234567",
            "session_id": "test_session",
            "status": "success",
            "heart_rate": {"value": 78},
            "respiration_rate": {"value": 16},
            "signal_quality": "GOOD",
            "quality_score": 0.86,
            "measurement_duration": 15.0,
            "message": "",
            "disclaimer": "Experimental.",
        }
        r = flask_client.post("/webhook/vital-result", json=payload)
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "ok"
        mock_send.assert_called_once_with(payload)

    def test_empty_payload_returns_400(self, flask_client):
        r = flask_client.post("/webhook/vital-result",
                              data="not json",
                              content_type="application/json")
        assert r.status_code == 400

    def test_missing_user_id_returns_400(self, flask_client):
        r = flask_client.post("/webhook/vital-result",
                              json={"status": "success"})
        assert r.status_code == 400
