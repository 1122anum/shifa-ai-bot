"""
conftest.py — Shared pytest fixtures used across all test modules.

Sets environment variables BEFORE any app module is imported so that
config.py does not raise a KeyError for missing Twilio credentials.
"""

import os
import pytest

# ---------------------------------------------------------------------------
# Inject dummy env vars before any app code is imported
# ---------------------------------------------------------------------------
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_auth_token_dummy")
os.environ.setdefault("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
os.environ.setdefault("BACKEND_BASE_URL", "http://localhost:8000")
os.environ.setdefault("WHISPER_ENDPOINT", "/api/transcribe")
os.environ.setdefault("AUDIO_TEMP_DIR", "audio_temp_test")
os.environ.setdefault("TWILIO_VALIDATE_SIGNATURE", "false")  # Disable sig check in tests


@pytest.fixture
def flask_client():
    """Return a Flask test client with signature validation disabled."""
    from app.webhook import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def twilio_form_text():
    """A minimal Twilio webhook POST payload for a text message."""
    return {
        "From": "whatsapp:+923001234567",
        "To": "whatsapp:+14155238886",
        "Body": "Mujhe bukhar aur khansi hai",
        "MessageSid": "SMtest000000000000000000000000000001",
        "NumMedia": "0",
    }


@pytest.fixture
def twilio_form_voice():
    """A minimal Twilio webhook POST payload for a voice message."""
    return {
        "From": "whatsapp:+923001234567",
        "To": "whatsapp:+14155238886",
        "Body": "",
        "MessageSid": "SMtest000000000000000000000000000002",
        "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages/MM123/Media/ME456",
        "MediaContentType0": "audio/ogg",
    }


@pytest.fixture
def twilio_form_image():
    """A minimal Twilio webhook POST payload for an image (unsupported media)."""
    return {
        "From": "whatsapp:+923001234567",
        "To": "whatsapp:+14155238886",
        "Body": "",
        "MessageSid": "SMtest000000000000000000000000000003",
        "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages/MM123/Media/ME789",
        "MediaContentType0": "image/jpeg",
    }
