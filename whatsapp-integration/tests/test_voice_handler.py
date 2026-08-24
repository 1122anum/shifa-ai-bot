"""
test_voice_handler.py — Unit tests for the voice message handler.

Covers Test 5 (voice → Whisper → Gemini → WhatsApp) and error scenarios.
"""

from unittest.mock import patch, MagicMock
import pytest


VOICE_URL = "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages/MM123/Media/ME456"
VOICE_CONTENT_TYPE = "audio/ogg"
FROM_NUMBER = "whatsapp:+923001234567"


class TestHandleVoiceMessage:

    # ------------------------------------------------------------------
    # Test 5 — Voice message full happy path (Urdu voice note)
    # ------------------------------------------------------------------
    @patch("app.handlers.voice_handler.cleanup_audio")
    @patch("app.handlers.voice_handler.send_whatsapp_message")
    @patch("app.handlers.voice_handler.call_triage")
    @patch("app.handlers.voice_handler.call_transcribe")
    @patch("app.handlers.voice_handler.download_audio")
    def test_voice_full_flow(
        self, mock_download, mock_transcribe, mock_triage, mock_send, mock_cleanup
    ):
        """Test 5: Voice → Whisper → Gemini → WhatsApp response."""
        mock_download.return_value = "audio_temp_test/test.ogg"
        mock_transcribe.return_value = "Mujhe kal raat se tez bukhar hai"
        mock_triage.return_value = (
            "Triage Level: URGENT\n\nTez bukhar ke liye fori doctor se milein."
        )

        from app.handlers.voice_handler import handle_voice_message

        handle_voice_message(FROM_NUMBER, VOICE_URL, VOICE_CONTENT_TYPE)

        mock_download.assert_called_once_with(VOICE_URL, VOICE_CONTENT_TYPE)
        mock_transcribe.assert_called_once_with("audio_temp_test/test.ogg")
        mock_triage.assert_called_once_with(
            user_id=FROM_NUMBER,
            symptoms="Mujhe kal raat se tez bukhar hai",
        )
        mock_send.assert_called_once()
        mock_cleanup.assert_called_once_with("audio_temp_test/test.ogg")

    # ------------------------------------------------------------------
    # Transcription failure — send VOICE_TRANSCRIPTION_FAILED_MSG
    # ------------------------------------------------------------------
    @patch("app.handlers.voice_handler.cleanup_audio")
    @patch("app.handlers.voice_handler.send_whatsapp_message")
    @patch("app.handlers.voice_handler.call_triage")
    @patch("app.handlers.voice_handler.call_transcribe")
    @patch("app.handlers.voice_handler.download_audio")
    def test_transcription_failure_sends_friendly_message(
        self, mock_download, mock_transcribe, mock_triage, mock_send, mock_cleanup
    ):
        """Whisper failure → user-friendly message, not a stack trace."""
        from app.services.backend_client import BackendError

        mock_download.return_value = "audio_temp_test/test.ogg"
        mock_transcribe.side_effect = BackendError("Whisper service unavailable")

        from app.handlers.voice_handler import handle_voice_message

        handle_voice_message(FROM_NUMBER, VOICE_URL, VOICE_CONTENT_TYPE)

        mock_triage.assert_not_called()
        mock_send.assert_called_once()
        sent_body = mock_send.call_args[0][1]
        assert "Whisper service unavailable" not in sent_body
        assert "voice" in sent_body.lower() or "text" in sent_body.lower()
        # Cleanup must still run
        mock_cleanup.assert_called_once()

    # ------------------------------------------------------------------
    # Triage failure after successful transcription
    # ------------------------------------------------------------------
    @patch("app.handlers.voice_handler.cleanup_audio")
    @patch("app.handlers.voice_handler.send_whatsapp_message")
    @patch("app.handlers.voice_handler.call_triage")
    @patch("app.handlers.voice_handler.call_transcribe")
    @patch("app.handlers.voice_handler.download_audio")
    def test_triage_failure_after_transcription(
        self, mock_download, mock_transcribe, mock_triage, mock_send, mock_cleanup
    ):
        """Triage failure after successful transcription → backend unavailable message."""
        from app.services.backend_client import BackendError

        mock_download.return_value = "audio_temp_test/test.ogg"
        mock_transcribe.return_value = "Mujhe sir dard hai"
        mock_triage.side_effect = BackendError("Gemini quota exceeded")

        from app.handlers.voice_handler import handle_voice_message

        handle_voice_message(FROM_NUMBER, VOICE_URL, VOICE_CONTENT_TYPE)

        mock_send.assert_called_once()
        sent_body = mock_send.call_args[0][1]
        assert "Gemini quota exceeded" not in sent_body
        assert "unavailable" in sent_body.lower() or "try again" in sent_body.lower()
        mock_cleanup.assert_called_once()

    # ------------------------------------------------------------------
    # Emergency in voice → must show emergency formatting
    # ------------------------------------------------------------------
    @patch("app.handlers.voice_handler.cleanup_audio")
    @patch("app.handlers.voice_handler.send_whatsapp_message")
    @patch("app.handlers.voice_handler.call_triage")
    @patch("app.handlers.voice_handler.call_transcribe")
    @patch("app.handlers.voice_handler.download_audio")
    def test_voice_emergency_response_formatted(
        self, mock_download, mock_transcribe, mock_triage, mock_send, mock_cleanup
    ):
        """Emergency detected in voice flow → ⚠️ EMERGENCY header in reply."""
        mock_download.return_value = "audio_temp_test/test.ogg"
        mock_transcribe.return_value = "I have severe chest pain and cannot breathe"
        mock_triage.return_value = (
            "Triage Level: EMERGENCY\nCall emergency services immediately."
        )

        from app.handlers.voice_handler import handle_voice_message

        handle_voice_message(FROM_NUMBER, VOICE_URL, VOICE_CONTENT_TYPE)

        mock_send.assert_called_once()
        sent_body = mock_send.call_args[0][1]
        assert "EMERGENCY" in sent_body
        assert "⚠️" in sent_body
