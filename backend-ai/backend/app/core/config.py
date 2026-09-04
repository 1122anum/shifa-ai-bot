"""
config.py — Centralised configuration for the Shifa AI backend.

All secrets and settings are loaded from environment variables via .env.
Never hard-code credentials here.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from the backend root (one level above app/)
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=str(_env_path), override=True)

logger = logging.getLogger(__name__)


class Settings:
    """Application settings loaded from environment variables."""

    # ── Google Gemini ────────────────────────────────────────────
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

    # ── Whisper / Speech-to-Text ─────────────────────────────────
    WHISPER_PROVIDER: str = os.getenv("WHISPER_PROVIDER", "openai").lower().strip()
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_WHISPER_MODEL: str = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_WHISPER_MODEL: str = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")

    # ── Network ──────────────────────────────────────────────────
    REQUEST_TIMEOUT_SECONDS: int = int(float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")))
    BACKEND_PUBLIC_URL: str = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
    WHATSAPP_INTEGRATION_URL: str = os.getenv("WHATSAPP_INTEGRATION_URL", "http://localhost:5000")

    # ── Emergency Engine ─────────────────────────────────────────
    EMERGENCY_DISPATCH_MODE: str = os.getenv("EMERGENCY_DISPATCH_MODE", "MOCK").strip().upper()
    DASHBOARD_SECRET_TOKEN: str = os.getenv("DASHBOARD_SECRET_TOKEN", "")
    EMERGENCY_COOLDOWN_MINUTES: int = int(os.getenv("EMERGENCY_COOLDOWN_MINUTES", "10"))

    # ── Meta WhatsApp (for vital result notifications) ───────────
    META_ACCESS_TOKEN: str = os.getenv("META_ACCESS_TOKEN", "")
    META_PHONE_NUMBER_ID: str = os.getenv("META_PHONE_NUMBER_ID", "")

    # ── Security ─────────────────────────────────────────────────
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    def validate(self) -> None:
        """Validate that required secrets are configured at startup.

        Raises SystemExit with a safe message if a required secret is missing.
        Never prints the actual secret value.
        """
        missing: list[str] = []

        if not self.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")

        # At least one whisper provider key is required
        if self.WHISPER_PROVIDER == "groq":
            if not self.GROQ_API_KEY:
                missing.append("GROQ_API_KEY")
        else:
            if not self.OPENAI_API_KEY:
                missing.append("OPENAI_API_KEY")

        if not self.DASHBOARD_SECRET_TOKEN:
            missing.append("DASHBOARD_SECRET_TOKEN")

        if missing:
            # Safe error — only names are shown, never values
            print(
                f"[FATAL] Missing required environment variables: {', '.join(missing)}",
                file=sys.stderr,
            )
            print(
                "Copy .env.example to .env and fill in your credentials.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        # Log configuration status (without revealing values)
        logger.info("Configuration validated | environment=%s", self.ENVIRONMENT)
        logger.info("Gemini API key configured: %s", bool(self.GEMINI_API_KEY))
        logger.info("Whisper provider: %s", self.WHISPER_PROVIDER)
        logger.info(
            "Speech-to-text key configured: %s",
            bool(self.GROQ_API_KEY if self.WHISPER_PROVIDER == "groq" else self.OPENAI_API_KEY),
        )
        logger.info("Emergency dispatch mode: %s", self.EMERGENCY_DISPATCH_MODE)
        logger.info("Dashboard token configured: %s", bool(self.DASHBOARD_SECRET_TOKEN))


# Singleton settings instance
settings = Settings()
