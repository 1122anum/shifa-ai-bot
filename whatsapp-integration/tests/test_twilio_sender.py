"""
test_twilio_sender.py — Unit tests for the Twilio message sender and formatters.
"""

from unittest.mock import patch, MagicMock
import pytest
from app.services.twilio_sender import format_triage_response


class TestFormatTriageResponse:

    def test_emergency_adds_warning_header(self):
        """EMERGENCY in response → ⚠️ header and seek care message."""
        ai_response = "Triage Level: EMERGENCY\nCall 1122 immediately."
        result = format_triage_response(ai_response)

        assert "⚠️" in result
        assert "*EMERGENCY*" in result
        assert "immediately" in result.lower() or "emergency" in result.lower()
        assert ai_response in result  # Original content preserved

    def test_routine_response_unchanged(self):
        """Non-emergency response is returned as-is."""
        ai_response = "Triage Level: ROUTINE\nDrink water and rest."
        result = format_triage_response(ai_response)
        assert result == ai_response

    def test_urgent_response_unchanged(self):
        """URGENT response (not EMERGENCY) is returned as-is."""
        ai_response = "Triage Level: URGENT\nSee a doctor today."
        result = format_triage_response(ai_response)
        assert result == ai_response

    def test_emergency_case_insensitive(self):
        """Emergency detection is case-insensitive."""
        ai_response = "triage level: emergency\nseek help."
        result = format_triage_response(ai_response)
        assert "⚠️" in result


class TestSendWhatsAppMessage:

    @patch("app.services.twilio_sender._get_client")
    def test_send_adds_whatsapp_prefix(self, mock_get_client):
        """If 'whatsapp:' prefix is missing, it should be added automatically."""
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.sid = "SMtest123"
        mock_client.messages.create.return_value = mock_message
        mock_get_client.return_value = mock_client

        from app.services.twilio_sender import send_whatsapp_message
        send_whatsapp_message("+923001234567", "Test message")

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["to"] == "whatsapp:+923001234567"

    @patch("app.services.twilio_sender._get_client")
    def test_send_does_not_double_prefix(self, mock_get_client):
        """If 'whatsapp:' prefix already exists, it should not be doubled."""
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.sid = "SMtest456"
        mock_client.messages.create.return_value = mock_message
        mock_get_client.return_value = mock_client

        from app.services.twilio_sender import send_whatsapp_message
        send_whatsapp_message("whatsapp:+923001234567", "Test message")

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["to"] == "whatsapp:+923001234567"
        assert "whatsapp:whatsapp:" not in call_kwargs["to"]
