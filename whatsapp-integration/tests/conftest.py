"""
conftest.py — Shared pytest fixtures.

Sets environment variables BEFORE any app module is imported.
All DB operations use an in-memory SQLite instance.
"""

import os
import pytest

# ── Dummy env vars ───────────────────────────────────────
os.environ.setdefault("META_ACCESS_TOKEN", "test_token_dummy")
os.environ.setdefault("META_PHONE_NUMBER_ID", "123456789")
os.environ.setdefault("META_VERIFY_TOKEN", "shifa_verify_token")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_auth_token_dummy")
os.environ.setdefault("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
os.environ.setdefault("BACKEND_BASE_URL", "http://localhost:8000")
os.environ.setdefault("WHISPER_ENDPOINT", "/api/transcribe")
os.environ.setdefault("AUDIO_TEMP_DIR", "audio_temp_test")
os.environ.setdefault("TWILIO_VALIDATE_SIGNATURE", "false")


# ── Patch DB to use temp file so tests don't touch production DB ──
@pytest.fixture(autouse=True)
def _patch_db_path(tmp_path, monkeypatch):
    """Redirect all DB operations to a temp file per test."""
    import app.database.db as db_module
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", test_db)
    db_module.init_db()
    yield


@pytest.fixture
def flask_client():
    """Return a Flask test client."""
    from app.webhook import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def meta_text_payload():
    """Minimal Meta webhook POST payload for a text message."""
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "923001234567",
                        "type": "text",
                        "id": "wamid_test_001",
                        "text": {"body": "Mujhe bukhar aur khansi hai"},
                    }]
                }
            }]
        }]
    }


@pytest.fixture
def meta_voice_payload():
    """Minimal Meta webhook POST payload for a voice message."""
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "923001234567",
                        "type": "audio",
                        "id": "wamid_test_002",
                        "audio": {
                            "id": "media_id_12345",
                            "mime_type": "audio/ogg",
                        },
                    }]
                }
            }]
        }]
    }


@pytest.fixture
def meta_image_payload():
    """Meta webhook payload for an unsupported image attachment."""
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "923001234567",
                        "type": "image",
                        "id": "wamid_test_003",
                        "image": {"id": "img_001", "mime_type": "image/jpeg"},
                    }]
                }
            }]
        }]
    }
