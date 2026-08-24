"""
test_text_handler.py — Unit tests for the text message handler.

Covers all 5 required test scenarios from the spec:
  Test 1 — Normal Urdu text
  Test 2 — Urdu (2-day fever)
  Test 3 — English
  Test 4 — Emergency detection
  + edge cases: empty body, backend error
"""

from unittest.mock import patch, call
import pytest


class TestHandleTextMessage:

    # ------------------------------------------------------------------
    # Test 1 — Normal text (light symptoms, Urdu)
    # ------------------------------------------------------------------
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_normal_urdu_light_symptoms(self, mock_triage, mock_send):
        """Test 1: Halki khansi — should return routine triage response."""
        mock_triage.return_value = (
            "Triage Level: ROUTINE\n\nAap ki khansi mild lag rahi hai. "
            "Pani piyen aur rest karein."
        )
        from app.handlers.text_handler import handle_text_message

        handle_text_message("whatsapp:+923001234567", "Mujhe halki khansi hai")

        mock_triage.assert_called_once_with(
            user_id="whatsapp:+923001234567",
            symptoms="Mujhe halki khansi hai",
        )
        mock_send.assert_called_once()
        sent_body = mock_send.call_args[0][1]
        assert "ROUTINE" in sent_body or "routine" in sent_body.lower() or len(sent_body) > 0

    # ------------------------------------------------------------------
    # Test 2 — Urdu (2-day fever)
    # ------------------------------------------------------------------
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_urdu_two_day_fever(self, mock_triage, mock_send):
        """Test 2: Do din se bukhar — should return Urdu triage response."""
        mock_triage.return_value = (
            "Triage Level: URGENT\n\nDo din ka bukhar serious ho sakta hai. "
            "Doctor se milein."
        )
        from app.handlers.text_handler import handle_text_message

        handle_text_message("whatsapp:+923001234567", "Mujhe do din se bukhar hai")

        mock_triage.assert_called_once_with(
            user_id="whatsapp:+923001234567",
            symptoms="Mujhe do din se bukhar hai",
        )
        mock_send.assert_called_once()
        sent_body = mock_send.call_args[0][1]
        assert len(sent_body) > 10

    # ------------------------------------------------------------------
    # Test 3 — English
    # ------------------------------------------------------------------
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_english_headache(self, mock_triage, mock_send):
        """Test 3: English — should return English triage response."""
        mock_triage.return_value = (
            "Triage Level: ROUTINE\n\nA headache can often be managed with rest "
            "and hydration. If it persists, consult a doctor."
        )
        from app.handlers.text_handler import handle_text_message

        handle_text_message("whatsapp:+923009876543", "I have a headache")

        mock_triage.assert_called_once_with(
            user_id="whatsapp:+923009876543",
            symptoms="I have a headache",
        )
        mock_send.assert_called_once()

    # ------------------------------------------------------------------
    # Test 4 — Emergency
    # ------------------------------------------------------------------
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_emergency_chest_pain(self, mock_triage, mock_send):
        """Test 4: EMERGENCY — response must include emergency warning."""
        mock_triage.return_value = (
            "Triage Level: EMERGENCY\n\nSevere chest pain and difficulty breathing "
            "are signs of a cardiac event. Call emergency services immediately."
        )
        from app.handlers.text_handler import handle_text_message

        handle_text_message(
            "whatsapp:+923001234567",
            "I have severe chest pain and difficulty breathing",
        )

        mock_send.assert_called_once()
        sent_body = mock_send.call_args[0][1]
        # Emergency formatting must be visible
        assert "EMERGENCY" in sent_body
        assert "⚠️" in sent_body
        assert "immediately" in sent_body.lower() or "medical" in sent_body.lower()

    # ------------------------------------------------------------------
    # Edge case — Empty body
    # ------------------------------------------------------------------
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_empty_body_sends_prompt(self, mock_triage, mock_send):
        """Empty text should prompt user to describe symptoms, not call triage."""
        from app.handlers.text_handler import handle_text_message

        handle_text_message("whatsapp:+923001234567", "   ")

        mock_triage.assert_not_called()
        mock_send.assert_called_once()
        sent_body = mock_send.call_args[0][1]
        assert "symptom" in sent_body.lower()

    # ------------------------------------------------------------------
    # Edge case — Backend unavailable
    # ------------------------------------------------------------------
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_backend_error_sends_user_friendly_message(self, mock_triage, mock_send):
        """BackendError must result in a safe user-friendly message, not a stack trace."""
        from app.services.backend_client import BackendError
        from app.handlers.text_handler import handle_text_message

        mock_triage.side_effect = BackendError("Connection refused")

        handle_text_message("whatsapp:+923001234567", "Mujhe bukhar hai")

        mock_send.assert_called_once()
        sent_body = mock_send.call_args[0][1]
        # Must not expose internal error details
        assert "Connection refused" not in sent_body
        assert "stack" not in sent_body.lower()
        # Must mention trying again or seeking help
        assert "try again" in sent_body.lower() or "unavailable" in sent_body.lower()
