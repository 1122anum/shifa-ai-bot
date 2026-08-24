"""
test_webhook.py — Tests for POST /webhook/whatsapp routing and response codes.

All external calls (Twilio, FastAPI backend) are mocked so these tests
run fully offline without any real credentials or services.
"""

from unittest.mock import patch, MagicMock
import pytest


class TestHealthEndpoint:
    def test_health_returns_200(self, flask_client):
        response = flask_client.get("/health")
        assert response.status_code == 200
        assert b"ok" in response.data


class TestWebhookRouting:

    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_text_message_routed_correctly(
        self, mock_triage, mock_send, flask_client, twilio_form_text
    ):
        """A text message should call call_triage and send a response."""
        mock_triage.return_value = "Triage Level: ROUTINE\nAap ki symptoms mild hain."
        response = flask_client.post("/webhook/whatsapp", data=twilio_form_text)

        assert response.status_code == 200
        mock_triage.assert_called_once_with(
            user_id="whatsapp:+923001234567",
            symptoms="Mujhe bukhar aur khansi hai",
        )
        mock_send.assert_called_once()

    @patch("app.handlers.voice_handler.send_whatsapp_message")
    @patch("app.handlers.voice_handler.call_triage")
    @patch("app.handlers.voice_handler.call_transcribe")
    @patch("app.handlers.voice_handler.download_audio")
    @patch("app.handlers.voice_handler.cleanup_audio")
    def test_voice_message_routed_correctly(
        self,
        mock_cleanup,
        mock_download,
        mock_transcribe,
        mock_triage,
        mock_send,
        flask_client,
        twilio_form_voice,
    ):
        """A voice message should download, transcribe, triage, and send a response."""
        mock_download.return_value = "audio_temp_test/test.ogg"
        mock_transcribe.return_value = "Mujhe do din se bukhar hai"
        mock_triage.return_value = "Triage Level: ROUTINE\nDo din ka bukhar manageable hai."

        response = flask_client.post("/webhook/whatsapp", data=twilio_form_voice)

        assert response.status_code == 200
        mock_download.assert_called_once()
        mock_transcribe.assert_called_once_with("audio_temp_test/test.ogg")
        mock_triage.assert_called_once_with(
            user_id="whatsapp:+923001234567",
            symptoms="Mujhe do din se bukhar hai",
        )
        mock_send.assert_called_once()
        mock_cleanup.assert_called_once_with("audio_temp_test/test.ogg")

    @patch("app.webhook.send_whatsapp_message")
    def test_unsupported_media_sends_guidance(
        self, mock_send, flask_client, twilio_form_image
    ):
        """An image attachment should send a 'text/voice only' reply."""
        response = flask_client.post("/webhook/whatsapp", data=twilio_form_image)
        assert response.status_code == 200
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][1]
        assert "text" in sent_text.lower() or "voice" in sent_text.lower()

    def test_missing_from_returns_200_empty_twiml(self, flask_client):
        """Malformed payload with no 'From' should still return 200 (prevents Twilio retries)."""
        response = flask_client.post("/webhook/whatsapp", data={"Body": "test"})
        assert response.status_code == 200

    def test_webhook_returns_xml(self, flask_client, twilio_form_text):
        """Webhook must return application/xml for Twilio."""
        with (
            patch("app.handlers.text_handler.call_triage", return_value="OK"),
            patch("app.handlers.text_handler.send_whatsapp_message"),
        ):
            response = flask_client.post("/webhook/whatsapp", data=twilio_form_text)
        assert "xml" in response.content_type
