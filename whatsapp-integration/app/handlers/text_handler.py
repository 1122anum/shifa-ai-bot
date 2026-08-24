"""
text_handler.py — Handles plain-text WhatsApp message flow.

Flow:
    User sends text
        → webhook extracts body + from_number
        → call_triage(user_id, symptoms)
        → format_triage_response(ai_response)
        → send_whatsapp_message(to, formatted_response)
"""

from app.services.backend_client import call_triage, BackendError
from app.services.meta_sender import (
    send_whatsapp_message,
    format_triage_response,
    BACKEND_UNAVAILABLE_MSG,
    GENERIC_ERROR_MSG,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def handle_text_message(from_number: str, body: str) -> None:
    """
    Process an incoming text message and send AI triage response.

    Args:
        from_number: Sender's phone number e.g. '923001234567'
        body:        Raw message text from the user.
    """
    logger.info("Text message | from=%s | len=%d", from_number, len(body))

    symptoms = body.strip()
    if not symptoms:
        send_whatsapp_message(
            from_number,
            "Please describe your symptoms and I will help you with a triage assessment.",
        )
        return

    try:
        ai_response = call_triage(user_id=from_number, symptoms=symptoms)
        reply = format_triage_response(ai_response)

    except BackendError as exc:
        logger.error("Backend error | from=%s | error=%s", from_number, exc)
        reply = BACKEND_UNAVAILABLE_MSG

    except Exception:
        logger.exception("Unexpected error | from=%s", from_number)
        reply = GENERIC_ERROR_MSG

    send_whatsapp_message(from_number, reply)
