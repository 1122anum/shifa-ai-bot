"""
test_webhook.py — Tests for POST /webhook/whatsapp routing.
Uses Meta JSON payload format (not Twilio form data).
"""

from unittest.mock import patch
import pytest


class TestHealthEndpoint:
    def test_health_returns_200(self, flask_client):
        response = flask_client.get("/health")
        assert response.status_code == 200
        assert b"ok" in response.data


class TestWebhookRouting:

    @patch("app.handlers.text_handler.send_whatsapp_message")
    @patch("app.handlers.text_handler.call_triage")
    def test_text_message_routed(self, mock_triage, mock_send, flask_client, meta_text_payload):
        mock_triage.return_value = "Triage Level: ROUTINE\nRest karein."
        response = flask_client.post(
            "/webhook/whatsapp",
            json=meta_text_payload,
            content_type="application/json",
        )
        assert response.status_code == 200
        mock_triage.assert_called_once()

    @patch("app.handlers.voice_handler.send_whatsapp_message")
    @patch("app.handlers.voice_handler.call_voice_triage")
    @patch("app.handlers.voice_handler.download_audio")
    @patch("app.handlers.voice_handler.cleanup_audio")
    def test_voice_message_routed(
        self, mock_cleanup, mock_download, mock_vt, mock_send,
        flask_client, meta_voice_payload
    ):
        mock_download.return_value = "audio_temp_test/test.ogg"
        mock_vt.return_value = {
            "transcript": "Mujhe bukhar hai",
            "ai_response": "Triage Level: ROUTINE\nDo din ka bukhar.",
        }
        response = flask_client.post(
            "/webhook/whatsapp",
            json=meta_voice_payload,
            content_type="application/json",
        )
        assert response.status_code == 200
        mock_download.assert_called_once()
        mock_vt.assert_called_once()

    @patch("app.webhook.send_whatsapp_message")
    def test_unsupported_media_sends_guidance(
        self, mock_send, flask_client, meta_image_payload
    ):
        response = flask_client.post(
            "/webhook/whatsapp",
            json=meta_image_payload,
            content_type="application/json",
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        sent = mock_send.call_args[0][1]
        assert "text" in sent.lower() or "voice" in sent.lower()

    def test_empty_payload_returns_200(self, flask_client):
        response = flask_client.post(
            "/webhook/whatsapp",
            json={},
            content_type="application/json",
        )
        assert response.status_code == 200

    def test_status_update_ignored(self, flask_client):
        """Delivery/read receipts have no messages key — should return 200 silently."""
        payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
        response = flask_client.post(
            "/webhook/whatsapp",
            json=payload,
            content_type="application/json",
        )
        assert response.status_code == 200
