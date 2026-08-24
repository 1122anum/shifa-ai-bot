import logging

from app.services.gemini_service import (
    GeminiServiceError,
    get_triage as _gemini_get_triage,
)

logger = logging.getLogger(__name__)

__all__ = ["get_triage", "TriageServiceError"]


class TriageServiceError(GeminiServiceError):
    """Raised when the triage workflow fails."""


def get_triage(symptoms: str):
    """Run the full triage workflow for a text message and return the final AI response.

    This is the single entry point used by FastAPI routes (and later by the
    WhatsApp/Twilio layer). Gemini-specific code stays inside gemini_service;
    this wrapper keeps validation and error translation in one place.
    """
    text = (symptoms or "").strip()
    if not text:
        raise ValueError("Symptoms must not be empty.")
    try:
        return _gemini_get_triage(text)
    except ValueError:
        raise
    except GeminiServiceError as exc:
        logger.error("Triage workflow failed: %s", exc)
        raise
