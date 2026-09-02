"""
test_voice_handler.py — Tests for voice handler using current call_voice_triage API.
"""

from unittest.mock import patch
import pytest

FROM = "923001234567"
MEDIA_ID = "media_id_12345"
CONTENT_TYPE = "audio/ogg"


class TestHandleVoiceMessage:

    # ── Test 5: Full voice flow ─────────────────────────
    @patch("app.handlers.voice_handler.fetch_vital_context", return_value="")
    @patch("app.handlers.voice_handler.cleanup_audio")
    @patch("app.handlers.voice_handler.send_whatsapp_message")
    @patch("app.handlers.voice_handler.call_voice_triage")
    @patch("app.handlers.voice_handler.download_audio")
    def test_voice_full_flow(self, mock_dl, mock_vt, mock_send, mock_clean, mock_vc):
        mock_dl.return_value = "audio_temp_test/test.ogg"
        mock_vt.return_value = {
            "transcript": "Mujhe kal raat se tez bukhar hai",
            "ai_response": "Triage Level: URGENT\nTez bukhar.",
        }
        from app.handlers.voice_handler import handle_voice_message
        handle_voice_message(FROM, MEDIA_ID, CONTENT_TYPE)

        mock_dl.assert_called_once_with(MEDIA_ID, CONTENT_TYPE)
        mock_vt.assert_called_once_with(
            user_id=FROM, audio_path="audio_temp_test/test.ogg", vital_context=""
        )
        mock_send.assert_called_once()
        mock_clean.assert_called_once_with("audio_temp_test/test.ogg")

    # ── Transcription failure ───────────────────────────
    @patch("app.handlers.voice_handler.fetch_vital_context", return_value="")
    @patch("app.handlers.voice_handler.cleanup_audio")
    @patch("app.handlers.voice_handler.send_whatsapp_message")
    @patch("app.handlers.voice_handler.call_voice_triage")
    @patch("app.handlers.voice_handler.download_audio")
    def test_transcription_failure(self, mock_dl, mock_vt, mock_send, mock_clean, mock_vc):
        from app.services.backend_client import BackendError
        mock_dl.return_value = "audio_temp_test/test.ogg"
        mock_vt.side_effect = BackendError("Whisper service unavailable")
        from app.handlers.voice_handler import handle_voice_message
        handle_voice_message(FROM, MEDIA_ID, CONTENT_TYPE)

        mock_send.assert_called_once()
        sent = mock_send.call_args[0][1]
        assert "Whisper service unavailable" not in sent
        mock_clean.assert_called_once()

    # ── Triage failure after transcription ─────────────
    @patch("app.handlers.voice_handler.fetch_vital_context", return_value="")
    @patch("app.handlers.voice_handler.cleanup_audio")
    @patch("app.handlers.voice_handler.send_whatsapp_message")
    @patch("app.handlers.voice_handler.call_voice_triage")
    @patch("app.handlers.voice_handler.download_audio")
    def test_backend_failure(self, mock_dl, mock_vt, mock_send, mock_clean, mock_vc):
        from app.services.backend_client import BackendError
        mock_dl.return_value = "audio_temp_test/test.ogg"
        mock_vt.side_effect = BackendError("Backend returned HTTP 502")
        from app.handlers.voice_handler import handle_voice_message
        handle_voice_message(FROM, MEDIA_ID, CONTENT_TYPE)

        mock_send.assert_called_once()
        sent = mock_send.call_args[0][1]
        assert "HTTP 502" not in sent
        mock_clean.assert_called_once()

    # ── Emergency in voice ──────────────────────────────
    @patch("app.handlers.voice_handler.fetch_vital_context", return_value="")
    @patch("app.handlers.voice_handler.cleanup_audio")
    @patch("app.handlers.voice_handler.send_whatsapp_message")
    @patch("app.handlers.voice_handler.call_voice_triage")
    @patch("app.handlers.voice_handler.download_audio")
    def test_emergency_formatting(self, mock_dl, mock_vt, mock_send, mock_clean, mock_vc):
        mock_dl.return_value = "audio_temp_test/test.ogg"
        mock_vt.return_value = {
            "transcript": "Severe chest pain",
            "ai_response": "Urgency Level: EMERGENCY\nCall emergency services.",
        }
        from app.handlers.voice_handler import handle_voice_message
        handle_voice_message(FROM, MEDIA_ID, CONTENT_TYPE)

        sent = mock_send.call_args[0][1]
        assert "EMERGENCY" in sent
        assert "⚠️" in sent
