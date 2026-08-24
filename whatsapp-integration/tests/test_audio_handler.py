"""
test_audio_handler.py — Unit tests for audio download and MIME type detection.
"""

import os
from unittest.mock import patch, MagicMock
import pytest
from app.services.audio_handler import is_audio_message, download_audio, cleanup_audio


class TestIsAudioMessage:

    def test_ogg_is_audio(self):
        assert is_audio_message("audio/ogg") is True

    def test_ogg_with_codec_is_audio(self):
        assert is_audio_message("audio/ogg; codecs=opus") is True

    def test_mp3_is_audio(self):
        assert is_audio_message("audio/mpeg") is True

    def test_image_is_not_audio(self):
        assert is_audio_message("image/jpeg") is False

    def test_empty_string_is_not_audio(self):
        assert is_audio_message("") is False

    def test_none_is_not_audio(self):
        assert is_audio_message(None) is False

    def test_video_is_not_audio(self):
        assert is_audio_message("video/mp4") is False


class TestDownloadAudio:

    @patch("app.services.audio_handler.requests.get")
    def test_download_creates_file(self, mock_get, tmp_path):
        """download_audio should write content to a file and return the path."""
        # Configure mock response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_content.return_value = [b"fake audio content"]
        mock_get.return_value = mock_response

        # Override AUDIO_TEMP_DIR to use tmp_path
        with patch("app.services.audio_handler.config") as mock_config:
            mock_config.AUDIO_TEMP_DIR = str(tmp_path)
            mock_config.TWILIO_ACCOUNT_SID = "ACtest"
            mock_config.TWILIO_AUTH_TOKEN = "testtoken"
            mock_config.REQUEST_TIMEOUT = 30

            path = download_audio(
                "https://api.twilio.com/fake/media/url",
                "audio/ogg",
            )

        assert os.path.exists(path)
        assert path.endswith(".ogg")

    @patch("app.services.audio_handler.requests.get")
    def test_download_uses_correct_extension_for_mp3(self, mock_get, tmp_path):
        """audio/mpeg content type should produce an .mp3 file."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_content.return_value = [b"fake mp3 content"]
        mock_get.return_value = mock_response

        with patch("app.services.audio_handler.config") as mock_config:
            mock_config.AUDIO_TEMP_DIR = str(tmp_path)
            mock_config.TWILIO_ACCOUNT_SID = "ACtest"
            mock_config.TWILIO_AUTH_TOKEN = "testtoken"
            mock_config.REQUEST_TIMEOUT = 30

            path = download_audio(
                "https://api.twilio.com/fake/media/url",
                "audio/mpeg",
            )

        assert path.endswith(".mp3")


class TestCleanupAudio:

    def test_cleanup_removes_existing_file(self, tmp_path):
        """cleanup_audio should delete the file if it exists."""
        f = tmp_path / "test.ogg"
        f.write_bytes(b"data")
        cleanup_audio(str(f))
        assert not f.exists()

    def test_cleanup_does_not_raise_for_missing_file(self):
        """cleanup_audio should not raise if the file doesn't exist."""
        cleanup_audio("/nonexistent/path/audio.ogg")  # Should not raise

    def test_cleanup_does_not_raise_for_none(self):
        """cleanup_audio should not raise if path is None."""
        cleanup_audio(None)  # Should not raise
