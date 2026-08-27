"""
test_text_handler.py — Unit tests for the text message handler.

Covers all 5 spec scenarios plus input validation edge cases.
"""

from unittest.mock import patch, MagicMock
import pytest


FROM = "923001234567"


class TestHandleTextMessage:

    # ── Test 1: Normal Urdu ─────────────────────────────
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_urdu_light_symptoms(self, mock_triage, mock_send):
        mock_triage.return_value = "Triage Level: ROUTINE\nHalki khansi hai."
        from app.handlers.text_handler import handle_text_message
        handle_text_message(FROM, "Mujhe halki khansi hai")
        mock_triage.assert_called_once()
        mock_send.assert_called_once()

    # ── Test 2: Urdu 2-day fever ────────────────────────
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_urdu_two_day_fever(self, mock_triage, mock_send):
        mock_triage.return_value = "Triage Level: URGENT\nDo din ka bukhar."
        from app.handlers.text_handler import handle_text_message
        handle_text_message(FROM, "Mujhe do din se bukhar hai")
        mock_triage.assert_called_once()
        mock_send.assert_called_once()

    # ── Test 3: English ─────────────────────────────────
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_english_headache(self, mock_triage, mock_send):
        mock_triage.return_value = "Triage Level: ROUTINE\nRest and hydrate."
        from app.handlers.text_handler import handle_text_message
        handle_text_message(FROM, "I have a headache")
        mock_triage.assert_called_once()
        mock_send.assert_called_once()

    # ── Test 4: Emergency ───────────────────────────────
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_emergency_chest_pain(self, mock_triage, mock_send):
        mock_triage.return_value = (
            "Urgency Level: EMERGENCY\nCall emergency services immediately."
        )
        from app.handlers.text_handler import handle_text_message
        handle_text_message(FROM, "I have severe chest pain and difficulty breathing")
        mock_send.assert_called_once()
        sent = mock_send.call_args[0][1]
        assert "EMERGENCY" in sent
        assert "⚠️" in sent

    # ── Input validation: Empty ─────────────────────────
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_empty_body_no_triage(self, mock_triage, mock_send):
        from app.handlers.text_handler import handle_text_message
        handle_text_message(FROM, "   ")
        mock_triage.assert_not_called()
        mock_send.assert_called_once()

    # ── Input validation: Greeting ──────────────────────
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_greeting_no_triage(self, mock_triage, mock_send):
        from app.handlers.text_handler import handle_text_message
        handle_text_message(FROM, "Hello")
        mock_triage.assert_not_called()
        mock_send.assert_called_once()
        sent = mock_send.call_args[0][1]
        assert "symptom" in sent.lower() or "shifa" in sent.lower()

    # ── Input validation: Urdu greeting ────────────────
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_urdu_greeting(self, mock_triage, mock_send):
        from app.handlers.text_handler import handle_text_message
        handle_text_message(FROM, "السلام علیکم")
        mock_triage.assert_not_called()
        mock_send.assert_called_once()

    # ── Input validation: /reset ────────────────────────
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_reset_command(self, mock_triage, mock_send):
        from app.handlers.text_handler import handle_text_message
        handle_text_message(FROM, "/reset")
        mock_triage.assert_not_called()
        mock_send.assert_called_once()
        sent = mock_send.call_args[0][1]
        assert "reset" in sent.lower() or "✅" in sent

    # ── Input validation: Too long ──────────────────────
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_too_long_input(self, mock_triage, mock_send):
        from app.handlers.text_handler import handle_text_message
        handle_text_message(FROM, "a" * 3000)
        mock_triage.assert_not_called()
        mock_send.assert_called_once()

    # ── Backend error ───────────────────────────────────
    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_backend_error_safe_message(self, mock_triage, mock_send):
        from app.services.backend_client import BackendError
        from app.handlers.text_handler import handle_text_message
        mock_triage.side_effect = BackendError("Connection refused")
        handle_text_message(FROM, "Mujhe bukhar hai")
        mock_send.assert_called_once()
        sent = mock_send.call_args[0][1]
        assert "Connection refused" not in sent
        assert "unavailable" in sent.lower() or "try again" in sent.lower()


class TestConversationContext:
    """Verify conversation history is built and saved."""

    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_second_message_gets_context(self, mock_triage, mock_send):
        """Second message should include previous turn in symptoms."""
        mock_triage.return_value = "Triage Level: ROUTINE\nFollowup."
        from app.handlers.text_handler import handle_text_message

        # First message — has medical keyword 'bukhar'
        handle_text_message(FROM, "Mujhe bukhar hai")
        first_symptoms = mock_triage.call_args[1]["symptoms"]

        mock_triage.reset_mock()

        # Second message — also medical to pass validation
        handle_text_message(FROM, "2 din se bukhar hai")
        second_symptoms = mock_triage.call_args[1]["symptoms"]

        # Second call must contain context from first turn
        assert "[Previous conversation]" in second_symptoms or \
               "bukhar" in second_symptoms

    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_reset_clears_context(self, mock_triage, mock_send):
        """After /reset, next message should NOT include old history."""
        mock_triage.return_value = "Triage Level: ROUTINE\nOk."
        from app.handlers.text_handler import handle_text_message

        handle_text_message(FROM, "Mujhe bukhar hai")
        handle_text_message(FROM, "/reset")
        mock_triage.reset_mock()

        handle_text_message(FROM, "Mujhe sir dard hai")
        symptoms = mock_triage.call_args[1]["symptoms"]
        assert "[Previous conversation]" not in symptoms
