"""
config.py — Centralised configuration loaded from environment variables.
Meta WhatsApp Business API version.
"""

import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))


class Config:
    # ------------------------------------------------------------------
    # Meta WhatsApp Business API
    # ------------------------------------------------------------------
    META_ACCESS_TOKEN: str   = os.environ.get("META_ACCESS_TOKEN", "")
    META_PHONE_NUMBER_ID: str = os.environ.get("META_PHONE_NUMBER_ID", "")
    META_VERIFY_TOKEN: str   = os.environ.get("META_VERIFY_TOKEN", "shifa_verify_token")

    # ------------------------------------------------------------------
    # Backend FastAPI service
    # ------------------------------------------------------------------
    BACKEND_BASE_URL: str  = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
    WHISPER_ENDPOINT: str  = os.getenv("WHISPER_ENDPOINT", "/api/transcribe")
    TRIAGE_URL: str        = f"{BACKEND_BASE_URL}/api/triage"
    TRANSCRIBE_URL: str    = f"{BACKEND_BASE_URL}{WHISPER_ENDPOINT}"

    # ------------------------------------------------------------------
    # Integration server
    # ------------------------------------------------------------------
    INTEGRATION_HOST: str = os.getenv("INTEGRATION_HOST", "0.0.0.0")
    INTEGRATION_PORT: int = int(os.getenv("INTEGRATION_PORT", "5000"))

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------
    AUDIO_TEMP_DIR: str = os.getenv("AUDIO_TEMP_DIR", "audio_temp")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ------------------------------------------------------------------
    # HTTP timeouts (seconds)
    # ------------------------------------------------------------------
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))


config = Config()
