"""
test_backend_client.py — Unit tests for the FastAPI backend HTTP client.

Uses the `responses` library to mock HTTP calls so no real server is needed.
"""

import responses as responses_mock
import pytest
from app.services.backend_client import call_triage, call_transcribe, BackendError
from app.config import config


class TestCallTriage:

    @responses_mock.activate
    def test_successful_triage_call(self):
        """call_triage returns the ai_response field from a 200 response."""
        responses_mock.add(
            responses_mock.POST,
            config.TRIAGE_URL,
            json={
                "status": "success",
                "user_id": "whatsapp:+923001234567",
                "ai_response": "Triage Level: ROUTINE\nRest and hydrate.",
            },
            status=200,
        )
        result = call_triage("whatsapp:+923001234567", "Mujhe khansi hai")
        assert result == "Triage Level: ROUTINE\nRest and hydrate."

    @responses_mock.activate
    def test_triage_http_500_raises_backend_error(self):
        """A 500 from the backend raises BackendError."""
        responses_mock.add(
            responses_mock.POST,
            config.TRIAGE_URL,
            json={"detail": "Internal Server Error"},
            status=500,
        )
        with pytest.raises(BackendError):
            call_triage("whatsapp:+923001234567", "test")

    @responses_mock.activate
    def test_triage_empty_ai_response_raises_backend_error(self):
        """An empty ai_response field raises BackendError."""
        responses_mock.add(
            responses_mock.POST,
            config.TRIAGE_URL,
            json={"status": "success", "ai_response": ""},
            status=200,
        )
        with pytest.raises(BackendError, match="empty ai_response"):
            call_triage("whatsapp:+923001234567", "test")

    def test_triage_connection_error_raises_backend_error(self):
        """Connection failure raises BackendError."""
        # No responses_mock active → real network attempt → ConnectionError
        import unittest.mock as mock
        import requests

        with mock.patch("requests.post", side_effect=requests.exceptions.ConnectionError):
            with pytest.raises(BackendError, match="Cannot connect"):
                call_triage("whatsapp:+923001234567", "test")


class TestCallTranscribe:

    @responses_mock.activate
    def test_successful_transcription(self, tmp_path):
        """call_transcribe returns the transcript text from a 200 response."""
        audio_file = tmp_path / "test.ogg"
        audio_file.write_bytes(b"fake audio data")

        responses_mock.add(
            responses_mock.POST,
            config.TRANSCRIBE_URL,
            json={"text": "Mujhe bukhar hai"},
            status=200,
        )
        result = call_transcribe(str(audio_file))
        assert result == "Mujhe bukhar hai"

    def test_missing_audio_file_raises_backend_error(self):
        """A non-existent audio file raises BackendError."""
        with pytest.raises(BackendError, match="Audio file not found"):
            call_transcribe("/nonexistent/path/audio.ogg")

    @responses_mock.activate
    def test_transcription_empty_text_raises_backend_error(self, tmp_path):
        """Empty transcript raises BackendError."""
        audio_file = tmp_path / "test.ogg"
        audio_file.write_bytes(b"fake audio data")

        responses_mock.add(
            responses_mock.POST,
            config.TRANSCRIBE_URL,
            json={"text": ""},
            status=200,
        )
        with pytest.raises(BackendError, match="empty text"):
            call_transcribe(str(audio_file))
