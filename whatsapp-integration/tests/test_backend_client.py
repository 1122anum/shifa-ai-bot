"""
test_backend_client.py — Tests for FastAPI backend HTTP client.
call_transcribe removed — only call_triage and call_voice_triage exist.
"""

import responses as responses_mock
import pytest
from app.services.backend_client import call_triage, call_voice_triage, BackendError
from app.config import config


class TestCallTriage:

    @responses_mock.activate
    def test_successful_triage(self):
        responses_mock.add(
            responses_mock.POST, config.TRIAGE_URL,
            json={"status": "success", "user_id": "923001234567",
                  "ai_response": "Triage Level: ROUTINE\nRest karein."},
            status=200,
        )
        result = call_triage("923001234567", "Mujhe bukhar hai")
        assert "ROUTINE" in result

    @responses_mock.activate
    def test_502_raises_backend_error(self):
        responses_mock.add(
            responses_mock.POST, config.TRIAGE_URL,
            json={"detail": "Service unavailable"}, status=502,
        )
        with pytest.raises(BackendError):
            call_triage("923001234567", "test")

    @responses_mock.activate
    def test_empty_ai_response_raises(self):
        responses_mock.add(
            responses_mock.POST, config.TRIAGE_URL,
            json={"status": "success", "ai_response": ""}, status=200,
        )
        with pytest.raises(BackendError, match="empty ai_response"):
            call_triage("923001234567", "test")

    def test_connection_error_raises(self):
        import unittest.mock as mock, requests
        with mock.patch("requests.post", side_effect=requests.exceptions.ConnectionError):
            with pytest.raises(BackendError, match="Cannot connect"):
                call_triage("923001234567", "test")


class TestCallVoiceTriage:

    @responses_mock.activate
    def test_successful_voice_triage(self, tmp_path):
        audio = tmp_path / "test.ogg"
        audio.write_bytes(b"fake audio")
        responses_mock.add(
            responses_mock.POST,
            f"{config.BACKEND_BASE_URL}/api/voice-triage",
            json={"status": "success", "user_id": "923001234567",
                  "transcript": "Mujhe bukhar hai",
                  "ai_response": "Triage Level: ROUTINE\nOk."},
            status=200,
        )
        result = call_voice_triage("923001234567", str(audio))
        assert result["transcript"] == "Mujhe bukhar hai"
        assert "ROUTINE" in result["ai_response"]

    def test_missing_file_raises(self):
        with pytest.raises(BackendError, match="Audio file not found"):
            call_voice_triage("923001234567", "/nonexistent/audio.ogg")
